import type { LiveAgentEvent } from '@/components/ai-trading/types'

export interface LiveRun {
    id: string
    events: Record<number, LiveAgentEvent[]>
    updatedAt?: string
    state: 'running' | 'completed' | 'failed' | 'skipped'
    finishedState?: 'completed' | 'failed'
}

type WireEvent = LiveAgentEvent & {
    request_id?: string
    event_id?: string
    status?: string
    reason?: string
    selected?: LiveAgentEvent[]
    event?: { symbol?: string; display_name?: string; security_id?: number }
}

export function isWireEvent(value: unknown): value is WireEvent {
    if (!value || typeof value !== 'object' || !('type' in value) || typeof value.type !== 'string') return false
    for (const key of ['request_id', 'event_id', 'symbol', 'display_name', 'sent_at_utc', 'message', 'reason', 'error', 'status', 'tool_name', 'report_text']) {
        if (key in value && Reflect.get(value, key) != null && typeof Reflect.get(value, key) !== 'string') return false
    }
    if ('rank' in value && (!Number.isInteger(value.rank) || Number(value.rank) < 1)) return false
    if ('sequence' in value && !Number.isFinite(value.sequence)) return false
    if ('selected' in value && (!Array.isArray(value.selected) || !value.selected.every((item: unknown) =>
        item !== null && typeof item === 'object' && isWireEvent({ ...item, type: 'stock_agent_selection' })))) return false
    if ('event' in value && value.event != null && (typeof value.event !== 'object' ||
        !isWireEvent({ ...value.event, type: 'stock_agent_selection' }))) return false
    return true
}

/** Request identity is essential: every concurrent Intra-Finder run uses rank 1. */
export function reduceLiveRuns(current: Record<string, LiveRun>, event: WireEvent): Record<string, LiveRun> {
    if (!event.type.startsWith('stock_agent_') && !event.type.startsWith('intra_finder_event_')) return current
    const id = event.request_id || event.event_id || 'legacy'
    const replacesLegacy = id === 'legacy' && ['stock_agent_selection', 'stock_agent_no_trade'].includes(event.type)
    const previous = replacesLegacy ? undefined : current[id]
    const events = { ...previous?.events }
    const append = (rank: number, item: LiveAgentEvent) => {
        const existing = events[rank] || []
        if (existing.some((entry) => entry.type === item.type && (
            item.sequence !== undefined ? entry.sequence === item.sequence :
                entry.sent_at_utc === item.sent_at_utc && entry.message === item.message
        ))) return
        events[rank] = [...existing, item].sort((a, b) => {
            if (a.sequence !== undefined && b.sequence !== undefined) return a.sequence - b.sequence
            return (a.sent_at_utc || '').localeCompare(b.sent_at_utc || '')
        })
    }
    if (event.type === 'stock_agent_selection' && Array.isArray(event.selected)) {
        for (const selected of event.selected) {
            if (!selected || !Number.isInteger(selected.rank) || Number(selected.rank) < 1) continue
            append(Number(selected.rank), { ...selected, type: event.type, sent_at_utc: event.sent_at_utc })
        }
    } else if (event.type === 'intra_finder_event_accepted') {
        append(1, { ...event.event, type: 'stock_agent_selection', rank: 1, sent_at_utc: event.sent_at_utc })
    } else if (event.type === 'stock_agent_no_trade') {
        append(event.rank || 1, { ...event, message: event.reason || event.message })
    } else if (event.rank) {
        append(event.rank, event)
    }
    const finishedState = event.type === 'intra_finder_event_finished'
        ? event.error || event.status === 'failed' ? 'failed' : 'completed'
        : previous?.finishedState
    let state: LiveRun['state'] = finishedState || 'running'
    const allEvents = Object.values(events)
    if (event.type === 'intra_finder_event_finished') {
        for (const rank of Object.keys(events).map(Number)) {
            if (!events[rank].some((item) => ['stock_agent_completed', 'stock_agent_failed', 'stock_agent_no_trade'].includes(item.type))) {
                append(rank, { type: state === 'failed' ? 'stock_agent_failed' : 'stock_agent_no_trade', rank,
                    message: event.error || 'Run finished without an agent decision.', sent_at_utc: event.sent_at_utc })
            }
        }
    } else if (!finishedState && allEvents.length && allEvents.every((items) => items.some((item) => ['stock_agent_completed', 'stock_agent_failed', 'stock_agent_no_trade'].includes(item.type)))) {
        state = allEvents.some((items) => items.some((item) => item.type === 'stock_agent_failed')) ? 'failed'
            : allEvents.some((items) => items.some((item) => item.type === 'stock_agent_completed')) ? 'completed' : 'skipped'
    }
    const updatedAt = [event.sent_at_utc || '', previous?.updatedAt || ''].sort().pop()
    const next = { ...current, [id]: { id, events, state, updatedAt, finishedState } }
    // Retain active work; bound finished history for a long-lived dashboard session.
    const finished = Object.values(next).filter((run) => run.state !== 'running')
        .sort((a, b) => (b.updatedAt || '').localeCompare(a.updatedAt || ''))
    for (const run of finished.slice(60)) delete next[run.id]
    return next
}
