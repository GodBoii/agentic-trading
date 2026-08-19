'use client'

import { useMemo, useState } from 'react'
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
import { formatClock, formatDateTime, formatShortDate, formatWeekday, pluralize } from '@/lib/format'
import type { TradeSessionSummary } from './types'
import { countAgents, groupSessionsByDate, sessionTimestamp } from './utils'

/**
 * Trade history, grouped by trading day.
 *
 * This screen exists to find a specific run, so runs are rows with time and
 * name, and the aggregate counts are stated rather than decorated.
 *
 * No run state is shown in the list, and that is deliberate. The list query
 * reads `agno_sessions` without the `runs` column — pulling it would mean
 * transferring every agent's full transcript to render one badge — so a
 * per-run status cannot be derived here. The previous version tried anyway and
 * rendered "UNKNOWN" on every row, which the day header then counted as
 * "26 running" on an archive of finished work. State now appears where it is
 * actually known: on the opened run.
 *
 * Motion, and why each piece is here:
 *
 *   - The day groups use the accordion recipe (recipe 21) via `AccordionShell`.
 *     The chevron flips rather than rotating 180°, which also fixes it on
 *     non-Chromium browsers.
 *
 *   - The three headline totals use the spinning counter (recipe 26). This is
 *     the one place in the product where that treatment fits: these numbers
 *     change once, when the archive loads, and they are the headline of the
 *     screen. Applying it to a live broker figure would be exhausting, which is
 *     why the dashboard uses the quieter number pop-in instead.
 *
 *   - Run rows cross-fade their arrow into a spinner while opening (recipe 09)
 *     rather than swapping between frames and collapsing the slot for a frame.
 *
 *   - Row hover is a background tint plus a left rail that wipes in (`.archive-row`).
 *     These rows used the hover-group lift (recipe 11), which was the wrong
 *     borrowing: the lift is for a row of peer cards, and on full-width rows
 *     inside a clipped panel it scaled the text blurry, nudged the neighbours,
 *     and cropped at the panel edge.
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
    const agentTotal = useMemo(() => countAgents(sessions), [sessions])

    // `undefined` means "the reader has not picked a day yet", which resolves to
    // the most recent one. The previous version seeded state with `groups[0].key`,
    // which is evaluated on the first render — while the list is still loading and
    // empty — so the default never took effect and every day loaded collapsed.
    const [chosenKey, setChosenKey] = useState<string | null | undefined>(undefined)
    const openKey = chosenKey === undefined ? (groups[0]?.key ?? null) : chosenKey

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
                    <StatTile label="Trading days" value={<SpinningCounter value={groups.length} />} />
                    <StatTile
                        label="Agents"
                        value={<SpinningCounter value={agentTotal} />}
                        note="One per analysed stock"
                    />
                    <StatTile label="Most recent" value={formatDateTime(groups[0]?.at)} />
                </CellGrid>

                <ul className="space-y-3">
                    {groups.map((group) => (
                        <li key={group.key}>
                            <DayGroup
                                at={group.at}
                                sessions={group.sessions}
                                open={openKey === group.key}
                                openingId={openingId}
                                onToggle={() => setChosenKey(openKey === group.key ? null : group.key)}
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
    return (
        <Panel as="article">
            <AccordionShell
                open={open}
                onToggle={onToggle}
                ariaLabel={`${formatWeekday(at)}, ${pluralize(sessions.length, 'run')}`}
                headerClassName="justify-between gap-3 px-4 py-3.5 sm:gap-4 sm:px-5"
                header={
                    <>
                        <span className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-2.5 gap-y-0.5">
                            <span className="text-[13.5px] font-medium tracking-[-0.02em] text-ink-primary sm:text-[14px]">
                                {formatWeekday(at)}
                            </span>
                            <span className="nums truncate font-mono text-[10px] text-ink-tertiary">
                                {formatShortDate(at)}
                            </span>
                        </span>

                        <span className="flex flex-shrink-0 items-center gap-2.5 sm:gap-3.5">
                            <span className="nums font-mono text-[10px] text-ink-tertiary">
                                {pluralize(sessions.length, 'run')}
                            </span>
                            <AccordionChevron size={15} className="text-ink-tertiary" />
                        </span>
                    </>
                }
            >
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
    const agents = session.agent_count || 0

    return (
        <button
            type="button"
            onClick={onOpen}
            onPointerEnter={onPrefetch}
            onFocus={onPrefetch}
            disabled={disabled}
            aria-busy={opening}
            className="archive-row card-button group flex min-h-[52px] items-center gap-3 px-4 py-3 disabled:cursor-wait sm:gap-4 sm:px-5"
        >
            <span className="nums w-[42px] flex-shrink-0 font-mono text-[11px] text-ink-secondary">
                {formatClock(sessionTimestamp(session), '—')}
            </span>

            <span className="min-w-0 flex-1 truncate text-[12.5px] text-ink-primary">{session.title}</span>

            {/* Only stated when it is a real distinction. "1 agent" on every row
                of a single-stock archive is a column of noise. */}
            {agents > 1 && (
                <span className="nums flex-shrink-0 font-mono text-[10px] text-ink-tertiary">
                    {pluralize(agents, 'agent')}
                </span>
            )}

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
                    <div className="flex items-center justify-between px-4 py-3.5 sm:px-5">
                        <Skeleton className="h-3.5 w-40" delay={item * 40} />
                        <Skeleton className="h-3 w-20" delay={item * 40} />
                    </div>
                </Panel>
            ))}
        </div>
    )
}
