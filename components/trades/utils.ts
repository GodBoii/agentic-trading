import type { Tone } from '@/components/ui/badge'
import type { TradeDateGroup, TradeSessionSummary } from './types'

export function sessionTimestamp(session: TradeSessionSummary) {
    return session.updated_at_utc || session.created_at_utc || ''
}

/**
 * Local calendar key. Uses `en-CA` because it formats as `YYYY-MM-DD`, which
 * sorts lexicographically — and does so in the viewer's timezone, so a run at
 * 23:50 IST groups under that day rather than the UTC one.
 */
function dateKey(value?: string | null) {
    if (!value) return 'unknown'
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return 'unknown'
    const parts = new Intl.DateTimeFormat('en-CA', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
    }).formatToParts(date)
    const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === type)?.value || ''
    return `${part('year')}-${part('month')}-${part('day')}`
}

export function groupSessionsByDate(sessions: TradeSessionSummary[]): TradeDateGroup[] {
    const groups = new Map<string, TradeSessionSummary[]>()
    for (const session of sessions) {
        const key = dateKey(sessionTimestamp(session))
        const existing = groups.get(key)
        if (existing) existing.push(session)
        else groups.set(key, [session])
    }
    return Array.from(groups, ([key, grouped]) => ({
        key,
        at: sessionTimestamp(grouped[0]),
        sessions: grouped,
    }))
}

/**
 * Replaces `statusColor()`, which returned `bg-success` / `bg-danger` /
 * `bg-warning` — none of which existed in the Tailwind config, so every status
 * dot in the archive rendered transparent.
 */
export function sessionStatusTone(status: string): Tone {
    if (status === 'completed') return 'positive'
    if (status === 'failed' || status === 'error') return 'negative'
    return 'warning'
}

export interface StatusTally {
    completed: number
    failed: number
    inProgress: number
}

export function tallyStatuses(sessions: TradeSessionSummary[]): StatusTally {
    return sessions.reduce<StatusTally>(
        (tally, session) => {
            const tone = sessionStatusTone(session.status)
            if (tone === 'positive') tally.completed += 1
            else if (tone === 'negative') tally.failed += 1
            else tally.inProgress += 1
            return tally
        },
        { completed: 0, failed: 0, inProgress: 0 },
    )
}

export function countAgents(sessions: TradeSessionSummary[]) {
    return sessions.reduce((total, session) => total + (session.agent_count || 0), 0)
}
