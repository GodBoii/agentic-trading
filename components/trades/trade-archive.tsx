'use client'

import { useMemo, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/ui/empty-state'
import { ArrowRight, ChevronDown } from '@/components/ui/icons'
import { Notice } from '@/components/ui/notice'
import { CellGrid, Panel } from '@/components/ui/panel'
import { Skeleton } from '@/components/ui/skeleton'
import { Spinner } from '@/components/ui/spinner'
import { StatTile } from '@/components/ui/stat'
import { cn } from '@/lib/cn'
import { count, formatClock, formatLongDate, formatWeekday, pluralize } from '@/lib/format'
import type { TradeSessionSummary } from './types'
import { countAgents, groupSessionsByDate, sessionStatusTone, sessionTimestamp, tallyStatuses } from './utils'

/**
 * Trade history, grouped by trading day.
 *
 * Rebuilt from an editorial layout — a `clamp(2.6rem, 6vw, 5.8rem)` headline,
 * serif-italic accents, and a GSAP scroll-scrubbed word reveal — into
 * information density. This screen exists to find a specific run, so runs are
 * rows with time, name, size and outcome, and the aggregate counts are stated
 * rather than animated. Dropping the scroll animation also removes GSAP and
 * ScrollTrigger from the bundle; the disclosure now uses the existing CSS
 * grid-template-rows transition.
 */
export function TradeArchive({
    sessions,
    loading,
    error,
    openingId,
    onOpen,
    onPrefetch,
    onRetry,
}: {
    sessions: TradeSessionSummary[]
    loading: boolean
    error: string | null
    openingId: string | null
    onOpen: (sessionId: string) => void
    onPrefetch: (sessionId: string) => void
    onRetry: () => void
}) {
    const groups = useMemo(() => groupSessionsByDate(sessions), [sessions])
    // Most recent day open by default — that is what is being looked for.
    const [openKey, setOpenKey] = useState<string | null>(groups[0]?.key ?? null)
    const totals = useMemo(() => tallyStatuses(sessions), [sessions])

    if (loading && !sessions.length) return <ArchiveSkeleton />

    if (!sessions.length) {
        return (
            <Panel>
                <EmptyState
                    title="No saved agent runs yet"
                    detail="Completed runs are archived here automatically. Once the scanner selects its first candidate, the run and its full analysis will appear."
                    minHeight={340}
                    action={
                        error ? (
                            <Button variant="subtle" onClick={onRetry}>
                                Try again
                            </Button>
                        ) : undefined
                    }
                />
            </Panel>
        )
    }

    return (
        <div className="space-y-4">
            {error && (
                <Notice
                    tone="warning"
                    action={
                        <Button size="sm" variant="subtle" onClick={onRetry}>
                            Retry
                        </Button>
                    }
                >
                    {error}
                </Notice>
            )}

            <CellGrid className="grid-cols-2 lg:grid-cols-4">
                <StatTile label="Archived runs" value={count(sessions.length)} emphasis="primary" />
                <StatTile
                    label="Trading days"
                    value={count(groups.length)}
                    note={`${pluralize(countAgents(sessions), 'agent')} in total`}
                />
                <StatTile label="Completed" value={count(totals.completed)} direction="positive" />
                <StatTile
                    label="Failed"
                    value={count(totals.failed)}
                    direction={totals.failed > 0 ? 'negative' : 'neutral'}
                    note={totals.inProgress ? `${totals.inProgress} still in progress` : undefined}
                />
            </CellGrid>

            <ul className="space-y-3">
                {groups.map((group) => (
                    <li key={group.key}>
                        <DayGroup
                            at={group.at}
                            sessions={group.sessions}
                            open={openKey === group.key}
                            panelId={`trade-day-${group.key}`}
                            openingId={openingId}
                            onToggle={() => setOpenKey((current) => (current === group.key ? null : group.key))}
                            onOpen={onOpen}
                            onPrefetch={onPrefetch}
                        />
                    </li>
                ))}
            </ul>
        </div>
    )
}

function DayGroup({
    at,
    sessions,
    open,
    panelId,
    openingId,
    onToggle,
    onOpen,
    onPrefetch,
}: {
    at: string
    sessions: TradeSessionSummary[]
    open: boolean
    panelId: string
    openingId: string | null
    onToggle: () => void
    onOpen: (sessionId: string) => void
    onPrefetch: (sessionId: string) => void
}) {
    const tally = tallyStatuses(sessions)

    return (
        <Panel as="article">
            <button
                type="button"
                aria-expanded={open}
                aria-controls={panelId}
                onClick={onToggle}
                className="trade-date-trigger flex w-full items-center justify-between gap-4 px-4 py-3.5 text-left sm:px-5"
            >
                <div className="flex min-w-0 items-baseline gap-3">
                    <h3 className="text-[14px] font-medium tracking-[-0.02em] text-ink-primary">
                        {formatWeekday(at)}
                    </h3>
                    <span className="nums truncate font-mono text-[10px] text-ink-tertiary">{formatLongDate(at)}</span>
                </div>

                <div className="flex flex-shrink-0 items-center gap-3 sm:gap-4">
                    {tally.completed > 0 && (
                        <Badge tone="positive" size="sm">
                            {tally.completed} done
                        </Badge>
                    )}
                    {tally.failed > 0 && (
                        <Badge tone="negative" size="sm">
                            {tally.failed} failed
                        </Badge>
                    )}
                    {tally.inProgress > 0 && (
                        <Badge tone="warning" size="sm">
                            {tally.inProgress} running
                        </Badge>
                    )}
                    <span className="nums hidden font-mono text-[10px] text-ink-tertiary sm:inline">
                        {pluralize(sessions.length, 'run')}
                    </span>
                    <ChevronDown
                        size={15}
                        className={cn(
                            'text-ink-tertiary transition-transform duration-200',
                            open && 'rotate-180',
                        )}
                    />
                </div>
            </button>

            <div id={panelId} className="trade-date-panel" data-open={open} aria-hidden={!open}>
                <div className="trade-date-panel-inner">
                    <ul className="border-t border-line">
                        {sessions.map((session) => (
                            <li key={session.session_id} className="border-b border-line last:border-b-0">
                                <RunRow
                                    session={session}
                                    opening={openingId === session.session_id}
                                    disabled={Boolean(openingId)}
                                    onOpen={() => onOpen(session.session_id)}
                                    onPrefetch={() => onPrefetch(session.session_id)}
                                />
                            </li>
                        ))}
                    </ul>
                </div>
            </div>
        </Panel>
    )
}

function RunRow({
    session,
    opening,
    disabled,
    onOpen,
    onPrefetch,
}: {
    session: TradeSessionSummary
    opening: boolean
    disabled: boolean
    onOpen: () => void
    onPrefetch: () => void
}) {
    return (
        <button
            type="button"
            onClick={onOpen}
            onPointerEnter={onPrefetch}
            onFocus={onPrefetch}
            disabled={disabled}
            aria-busy={opening}
            className="card-button group flex items-center gap-3 px-4 py-3 disabled:cursor-wait sm:gap-4 sm:px-5"
        >
            <span className="nums w-11 flex-shrink-0 font-mono text-[11px] text-ink-secondary">
                {formatClock(sessionTimestamp(session), '—')}
            </span>

            <span className="min-w-0 flex-1">
                <span className="block truncate text-[12.5px] text-ink-primary">{session.title}</span>
                <span className="block truncate font-mono text-[9px] text-ink-tertiary">
                    {pluralize(session.agent_count || 0, 'agent')}
                    {session.loaded_from_cloud ? ' · cloud archive' : ' · saved archive'}
                </span>
            </span>

            <Badge tone={sessionStatusTone(session.status)} size="sm" className="flex-shrink-0">
                {session.status}
            </Badge>

            <span className="flex w-4 flex-shrink-0 justify-end">
                {opening ? (
                    <Spinner />
                ) : (
                    <ArrowRight
                        size={14}
                        className="text-ink-tertiary transition-transform duration-150 group-hover:translate-x-0.5 group-hover:text-ink-secondary"
                    />
                )}
            </span>
        </button>
    )
}

function ArchiveSkeleton() {
    return (
        <div className="space-y-4" aria-busy="true" aria-label="Loading trade history">
            <CellGrid className="grid-cols-2 lg:grid-cols-4">
                {[0, 1, 2, 3].map((item) => (
                    <div key={item} className="p-4 sm:p-5">
                        <Skeleton className="h-2.5 w-20" />
                        <Skeleton className="mt-4 h-5 w-16" />
                    </div>
                ))}
            </CellGrid>
            {[0, 1, 2].map((item) => (
                <Panel key={item}>
                    <div className="flex items-center justify-between px-5 py-3.5">
                        <Skeleton className="h-3.5 w-40" />
                        <Skeleton className="h-3 w-20" />
                    </div>
                </Panel>
            ))}
        </div>
    )
}
