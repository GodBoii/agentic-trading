'use client'

import { useMemo, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/ui/empty-state'
import { Notice } from '@/components/ui/notice'
import { CellGrid, Panel } from '@/components/ui/panel'
import { Skeleton } from '@/components/ui/skeleton'
import { Spinner } from '@/components/ui/spinner'
import { StatTile } from '@/components/ui/stat'
import { AccordionChevron, AccordionShell } from '@/components/motion/accordion'
import { IconSwap } from '@/components/motion/icon-swap'
import { LearnMoreChevron } from '@/components/motion/learn-more'
import { SkeletonReveal } from '@/components/motion/skeleton-reveal'
import { SpinningCounter } from '@/components/motion/number-flow'
import { useHoverGroup } from '@/components/motion/hover-group'
import { count, formatClock, formatLongDate, formatWeekday, pluralize } from '@/lib/format'
import type { TradeSessionSummary } from './types'
import { countAgents, groupSessionsByDate, sessionStatusTone, sessionTimestamp, tallyStatuses } from './utils'

/**
 * Trade history, grouped by trading day.
 *
 * This screen exists to find a specific run, so runs are rows with time, name,
 * size and outcome, and the aggregate counts are stated rather than decorated.
 *
 * Motion, and why each piece is here:
 *
 *   - The day groups use the accordion recipe (recipe 21) via `AccordionShell`,
 *     replacing this file's own bespoke `grid-template-rows` transition. It was
 *     already the right technique; the change is that the archive, the agent
 *     disclosures and every other collapsible now share one expand feel instead
 *     of three near-identical implementations. The chevron flips rather than
 *     rotating 180°, which also fixes it on non-Chromium browsers.
 *
 *   - The four headline totals use the spinning counter (recipe 26). This is the
 *     one place in the product where that treatment fits: these numbers change
 *     once, when the archive loads, and they are the headline of the screen.
 *     Applying it to a live broker figure would be exhausting, which is why the
 *     dashboard uses the quieter number pop-in instead.
 *
 *   - Run rows cross-fade their arrow into a spinner while opening (recipe 09)
 *     rather than swapping between frames and collapsing the slot for a frame.
 *
 *   - The rows in an open day form a hover group (recipe 11), so scanning down a
 *     day's runs combs the list.
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

    // Only the first load gets a placeholder. A refresh that already has rows
    // on screen keeps them, because replacing real history with a skeleton
    // discards information the reader was mid-scan through.
    if (!loading && !sessions.length) {
        return (
            <Panel>
                <EmptyState
                    title="No saved agent runs yet"
                    detail="Completed runs are archived here automatically. Once the scanner selects its first candidate, the run and its full analysis will appear."
                    minHeight={340}
                    action={
                        error ? (
                            <Button variant="subtle" onClick={onRetry} swapLabel>
                                Try again
                            </Button>
                        ) : undefined
                    }
                />
            </Panel>
        )
    }

    return (
        <SkeletonReveal
            loading={loading && !sessions.length}
            skeleton={<ArchiveSkeleton />}
            label="Loading trade history"
            flow
            className="space-y-4"
        >
            <div className="space-y-4">
            {error && (
                <Notice
                    tone="warning"
                    action={
                        <Button size="sm" variant="subtle" onClick={onRetry} swapLabel>
                            Retry
                        </Button>
                    }
                >
                    {error}
                </Notice>
            )}

            <CellGrid className="grid-cols-2 lg:grid-cols-4">
                <StatTile
                    label="Archived runs"
                    value={<SpinningCounter value={sessions.length} />}
                    emphasis="primary"
                />
                <StatTile
                    label="Trading days"
                    value={<SpinningCounter value={groups.length} />}
                    note={`${pluralize(countAgents(sessions), 'agent')} in total`}
                />
                <StatTile
                    label="Completed"
                    value={<SpinningCounter value={totals.completed} />}
                    direction="positive"
                />
                <StatTile
                    label="Failed"
                    value={<SpinningCounter value={totals.failed} />}
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
                            openingId={openingId}
                            onToggle={() => setOpenKey((current) => (current === group.key ? null : group.key))}
                            onOpen={onOpen}
                            onPrefetch={onPrefetch}
                        />
                    </li>
                ))}
            </ul>
            </div>
        </SkeletonReveal>
    )
}

function DayGroup({
    at,
    sessions,
    open,
    openingId,
    onToggle,
    onOpen,
    onPrefetch,
}: {
    at: string
    sessions: TradeSessionSummary[]
    open: boolean
    openingId: string | null
    onToggle: () => void
    onOpen: (sessionId: string) => void
    onPrefetch: (sessionId: string) => void
}) {
    const tally = tallyStatuses(sessions)
    const { groupProps, itemProps } = useHoverGroup<HTMLUListElement>()

    return (
        <Panel as="article">
            <AccordionShell
                open={open}
                onToggle={onToggle}
                ariaLabel={`${formatWeekday(at)}, ${pluralize(sessions.length, 'run')}`}
                headerClassName="justify-between gap-4 px-4 py-3.5 sm:px-5"
                header={
                    <>
                        <div className="flex min-w-0 items-baseline gap-3">
                            <h3 className="text-[14px] font-medium tracking-[-0.02em] text-ink-primary">
                                {formatWeekday(at)}
                            </h3>
                            <span className="nums truncate font-mono text-[10px] text-ink-tertiary">
                                {formatLongDate(at)}
                            </span>
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
                            <AccordionChevron size={15} className="text-ink-tertiary" />
                        </div>
                    </>
                }
            >
                <ul {...groupProps} className="border-t border-line">
                    {sessions.map((session, index) => {
                        const { className: itemClass, ...itemHandlers } = itemProps(index)
                        return (
                            <li
                                key={session.session_id}
                                className={`border-b border-line last:border-b-0 ${itemClass}`}
                                {...itemHandlers}
                            >
                                <RunRow
                                    session={session}
                                    opening={openingId === session.session_id}
                                    disabled={Boolean(openingId)}
                                    onOpen={() => onOpen(session.session_id)}
                                    onPrefetch={() => onPrefetch(session.session_id)}
                                />
                            </li>
                        )
                    })}
                </ul>
            </AccordionShell>
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

            {/* Cross-faded rather than conditionally rendered, so the slot never
                collapses and the row's other columns do not shift. */}
            <span className="flex w-4 flex-shrink-0 justify-end text-ink-tertiary transition-colors duration-[250ms] group-hover:text-ink-secondary">
                <IconSwap
                    showB={opening}
                    a={<LearnMoreChevron size={14} />}
                    b={<Spinner size={12} />}
                    label={opening ? 'Opening run' : undefined}
                />
            </span>
        </button>
    )
}

function ArchiveSkeleton() {
    return (
        <div className="space-y-4">
            <CellGrid className="grid-cols-2 lg:grid-cols-4">
                {[0, 1, 2, 3].map((item) => (
                    <div key={item} className="p-4 sm:p-5">
                        <Skeleton className="h-2.5 w-20" delay={item * 40} />
                        <Skeleton className="mt-4 h-5 w-16" delay={item * 40} />
                    </div>
                ))}
            </CellGrid>
            {[0, 1, 2].map((item) => (
                <Panel key={item}>
                    <div className="flex items-center justify-between px-5 py-3.5">
                        <Skeleton className="h-3.5 w-40" delay={item * 40} />
                        <Skeleton className="h-3 w-20" delay={item * 40} />
                    </div>
                </Panel>
            ))}
        </div>
    )
}
