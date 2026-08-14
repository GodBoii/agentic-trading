import type { TradeDateGroup, TradeSessionSummary } from './types'

export function groupSessionsByDate(sessions: TradeSessionSummary[]): TradeDateGroup[] {
    const groups = new Map<string, TradeSessionSummary[]>()
    for (const session of sessions) {
        const key = sessionDateKey(sessionTimestamp(session))
        groups.set(key, [...(groups.get(key) || []), session])
    }
    return Array.from(groups, ([key, groupedSessions]) => ({ key, sessions: groupedSessions }))
}

export function sessionTimestamp(session: TradeSessionSummary) {
    return session.updated_at_utc || session.created_at_utc || ''
}

export function formatSessionDate(value?: string | null) {
    if (!value) return { day: 'Unknown', date: 'Date unavailable' }
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return { day: 'Unknown', date: 'Date unavailable' }
    return {
        day: new Intl.DateTimeFormat('en-IN', { weekday: 'long' }).format(date),
        date: new Intl.DateTimeFormat('en-IN', {
            day: '2-digit', month: 'long', year: 'numeric',
        }).format(date),
    }
}

export function formatSessionTime(value?: string | null) {
    if (!value) return 'Time unavailable'
    try {
        return new Intl.DateTimeFormat('en-IN', {
            hour: '2-digit', minute: '2-digit',
        }).format(new Date(value))
    } catch {
        return 'Time unavailable'
    }
}

export function pluralize(count: number, singular: string, plural = `${singular}s`) {
    return `${count} ${count === 1 ? singular : plural}`
}

export function statusColor(status: string) {
    if (status === 'completed') return 'bg-success'
    if (status === 'failed') return 'bg-danger'
    return 'bg-warning'
}

function sessionDateKey(value?: string | null) {
    if (!value) return 'unknown'
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return 'unknown'
    const parts = new Intl.DateTimeFormat('en-CA', {
        year: 'numeric', month: '2-digit', day: '2-digit',
    }).formatToParts(date)
    const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === type)?.value || ''
    return `${part('year')}-${part('month')}-${part('day')}`
}
