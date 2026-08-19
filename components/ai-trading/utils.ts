import type {
    AgentFileCard,
    AgentImageCard,
    AgentResult,
    AgentRunStatus,
    LiveAgentEvent,
} from './types'

/**
 * Agent-domain helpers. Purely about interpreting the agent event protocol —
 * date and number formatting lives in `lib/format.ts`, which this module used
 * to duplicate (its own `formatTime`, `formatDateTime` and `pluralize`).
 */

export function websocketUrl() {
    if (typeof window === 'undefined') return null
    const configured = process.env.NEXT_PUBLIC_AI_TRADING_WS_URL
    if (configured) return configured
    if (!['localhost', '127.0.0.1', '::1'].includes(window.location.hostname)) return null
    return `ws://${window.location.hostname}:8020/ai-trading/stream`
}

const EVENT_TITLES: Record<string, string> = {
    stock_agent_selection: 'Selected',
    stock_agent_started: 'Started',
    stock_agent_input: 'Input received',
    stock_agent_charts_ready: 'Charts ready',
    stock_agent_thinking: 'Analysis',
    stock_agent_response_delta: 'Response',
    stock_agent_completed: 'Completed',
    stock_agent_failed: 'Failed',
    stock_agent_no_trade: 'No trade',
    stock_agent_run_error: 'Run error',
}

export function eventTitle(event: LiveAgentEvent) {
    if (event.type.startsWith('stock_agent_tool_call_')) {
        const suffix = event.type.endsWith('_completed')
            ? 'completed'
            : event.type.endsWith('_error')
              ? 'failed'
              : 'running'
        return `${event.tool_name || 'Tool'} ${suffix}`
    }
    return EVENT_TITLES[event.type] || event.type.replaceAll('_', ' ')
}

export type EventTone = 'neutral' | 'active' | 'positive' | 'negative' | 'info'

export function eventTone(event: LiveAgentEvent): EventTone {
    if (event.type === 'stock_agent_completed') return 'positive'
    if (
        event.type === 'stock_agent_failed' ||
        event.type === 'stock_agent_run_error' ||
        event.type === 'stock_agent_tool_call_error'
    ) {
        return 'negative'
    }
    if (event.type === 'stock_agent_no_trade') return 'active'
    if (event.type.startsWith('stock_agent_tool_call_')) return 'info'
    if (event.type === 'stock_agent_thinking' || event.type === 'stock_agent_response_delta') return 'neutral'
    return 'active'
}

export const TONE_DOT: Record<EventTone, string> = {
    neutral: 'bg-ink-tertiary',
    active: 'bg-warning',
    positive: 'bg-positive',
    negative: 'bg-negative',
    info: 'bg-ink-secondary',
}

/** Merge consecutive streaming deltas so the timeline renders prose, not fragments. */
export function coalesceAgentEvents(events: LiveAgentEvent[]) {
    const merged: LiveAgentEvent[] = []
    for (const event of events) {
        const previous = merged[merged.length - 1]
        const mergeable = event.type === 'stock_agent_thinking' || event.type === 'stock_agent_response_delta'
        if (previous && mergeable && previous.type === event.type) {
            previous.message = `${previous.message || ''}${event.message || ''}`
            previous.sequence = event.sequence || previous.sequence
            previous.sent_at_utc = event.sent_at_utc || previous.sent_at_utc
            continue
        }
        merged.push({ ...event })
    }
    return merged
}

export function agentDisplayName(
    agent?: Partial<AgentResult | LiveAgentEvent> | null,
    fallback = 'Awaiting stock',
) {
    return agent?.display_name || agent?.symbol || fallback
}

export function attachmentImageUrl(image: AgentImageCard) {
    return (
        image.cloud_url ||
        image.url ||
        (image.path ? `/api/ai-trading/assets?path=${encodeURIComponent(String(image.path))}` : '')
    )
}

export function attachmentFileUrl(file: AgentFileCard) {
    return (
        file.cloud_url ||
        file.url ||
        (file.path ? `/api/ai-trading/assets?path=${encodeURIComponent(String(file.path))}` : '')
    )
}

/**
 * Resolve the event stream for one agent slot: live events when present,
 * otherwise the persisted timeline plus a synthesized completion event. This is
 * what lets the archive replay through the same components as a live run.
 */
export function mergedEventsForRank(
    rank: number,
    liveEvents: Record<number, LiveAgentEvent[]>,
    completedResults: AgentResult[],
    runStatus: AgentRunStatus | null,
): LiveAgentEvent[] {
    let events = liveEvents[rank] || []
    const completed = completedResults.find((item) => Number(item.rank) === rank)

    if (!events.length && Array.isArray(completed?.agent_metadata?.timeline)) {
        events = completed.agent_metadata.timeline.map((event: LiveAgentEvent) => ({
            ...event,
            rank,
            symbol: event.symbol || completed.symbol,
            display_name: event.display_name || completed.display_name,
            sent_at_utc:
                event.sent_at_utc || (event.created_at ? new Date(event.created_at * 1000).toISOString() : undefined),
        }))
    }

    if (completed && !events.some((event) => event.type === 'stock_agent_completed')) {
        return coalesceAgentEvents([
            ...events,
            {
                type: 'stock_agent_completed',
                rank,
                symbol: completed.symbol,
                display_name: completed.display_name,
                message: 'Completed from latest saved status.',
                decision: completed.decision,
                attachments: completed.attachments,
                agent_metadata: completed.agent_metadata || undefined,
                report_text: completed.report_text || completed.analysis,
                sent_at_utc: runStatus?.stages?.stock_agent?.generated_at_utc || runStatus?.updated_at_utc,
            },
        ])
    }

    return coalesceAgentEvents(events)
}

/** Ordered agent slot ranks from live traffic and/or persisted results. */
export function agentSlotRanks(
    liveEvents: Record<number, LiveAgentEvent[]>,
    completedResults: AgentResult[],
    fallback: number,
) {
    const ranks = Array.from(
        new Set([
            ...Object.keys(liveEvents)
                .map((rank) => Number(rank))
                .filter(Boolean),
            ...completedResults.map((item) => Number(item.rank)).filter(Boolean),
        ]),
    ).sort((a, b) => a - b)
    return ranks.length ? ranks : [fallback]
}

const LIFECYCLE_EVENTS = ['stock_agent_selection', 'stock_agent_started', 'stock_agent_charts_ready']

/**
 * True when the stream records how the run progressed, not just that it ended.
 *
 * A run replayed from `agno_sessions` has no stored timeline, so
 * `mergedEventsForRank` gives it one synthesized `completed` event. Deriving a
 * stepper from that reports three unreached stages on work that finished, which
 * is why the workspace asks this before drawing one.
 */
export function hasLifecycleEvents(events: LiveAgentEvent[]) {
    return events.some((event) => LIFECYCLE_EVENTS.includes(event.type))
}

export interface AgentMilestone {
    key: string
    label: string
    at?: string
    reached: boolean
    failed?: boolean
}

/** Lifecycle checkpoints for one agent, derived from its event stream. */
export function agentMilestones(events: LiveAgentEvent[]): AgentMilestone[] {
    const find = (type: string) => events.find((event) => event.type === type)
    const failed = find('stock_agent_failed')

    const milestones: AgentMilestone[] = [
        {
            key: 'selected',
            label: 'Selected',
            at: find('stock_agent_selection')?.sent_at_utc,
            reached: Boolean(find('stock_agent_selection')),
        },
        {
            key: 'started',
            label: 'Started',
            at: find('stock_agent_started')?.sent_at_utc,
            reached: Boolean(find('stock_agent_started')),
        },
        {
            key: 'charts',
            label: 'Charts ready',
            at: find('stock_agent_charts_ready')?.sent_at_utc,
            reached: Boolean(find('stock_agent_charts_ready')),
        },
    ]

    if (failed) {
        milestones.push({ key: 'failed', label: 'Failed', at: failed.sent_at_utc, reached: true, failed: true })
    } else {
        const completed = find('stock_agent_completed')
        milestones.push({
            key: 'completed',
            label: 'Completed',
            at: completed?.sent_at_utc,
            reached: Boolean(completed),
        })
    }

    return milestones
}
