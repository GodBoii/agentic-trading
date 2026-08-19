'use client'

import { useEffect, useMemo, useState } from 'react'
import { EmptyState } from '@/components/ui/empty-state'
import { Panel, PanelHeader } from '@/components/ui/panel'
import { PageSwitch } from '@/components/motion/page-switch'
import { count } from '@/lib/format'
import { agentDisplayName, agentSlotRanks, mergedEventsForRank } from '@/components/ai-trading/utils'
import type { AgentResult, AgentRunStatus, LiveAgentEvent, StreamState } from '@/components/ai-trading/types'
import { AgentRoster, type AgentSlot } from './agent-roster'
import { AgentWorkspace } from './agent-workspace'
import { StreamIndicator, streamHint } from './stream-indicator'

/**
 * Roster ⇄ workspace switch for a run, live or archived.
 *
 * With `soloDirect`, a run holding one agent skips the roster and renders the
 * workspace on its own. Trade history uses it: nearly every archived run has a
 * single agent, and the roster in between was a panel containing one card that
 * repeated the run title from the header above it, costing a click that offered
 * no choice.
 *
 * Motion (recipe 08, page side-by-side). Opening an agent and coming back out
 * are the clearest list ⇄ detail pair in the product, so they slide: the roster
 * exits left as the workspace enters from the right, and the reverse on the way
 * back. The 8px travel is small enough not to feel like a page load, but the
 * direction tells the reader whether they went deeper or came back out — which
 * is exactly what a cross-fade cannot say, and what the previous hard swap said
 * nothing about.
 *
 * Symmetric at 250ms: forward and back are one motion reversed, so the
 * durations are not split.
 *
 * The run panel carries a travelling border beam while a stream is live. It is
 * gated on real state and it is the only beam in the product shell, because
 * several animated edges at once compete with each other and with the data.
 */
export function AgentConsole({
    runStatus,
    liveEvents,
    sessionAgents,
    stream,
    emptyState,
    soloDirect = false,
}: {
    runStatus: AgentRunStatus | null
    liveEvents: Record<number, LiveAgentEvent[]>
    sessionAgents?: AgentResult[]
    stream: StreamState
    emptyState?: { title: string; detail: string }
    /**
     * Skip the roster when the run holds exactly one agent and open it directly.
     * A one-card roster is a click that carries no choice, and the card repeats
     * the run title the caller has already shown. Off by default: on the live
     * page the roster is where a run grows from one agent to several, so a
     * second agent arriving must not yank the reader out of the first.
     */
    soloDirect?: boolean
}) {
    const results: AgentResult[] = useMemo(
        () => (sessionAgents?.length ? sessionAgents : runStatus?.stages?.stock_agent?.details?.results || []),
        [sessionAgents, runStatus],
    )

    const slots: AgentSlot[] = useMemo(() => {
        const ranks = agentSlotRanks(liveEvents, results, 1)
        return ranks.map((rank) => {
            const events = mergedEventsForRank(rank, liveEvents, results, runStatus)
            const latest = events[events.length - 1]
            const persisted = results.find((item) => Number(item.rank) === rank)
            return {
                rank,
                name: agentDisplayName(latest || persisted, `Agent ${rank}`),
                events,
                complete: latest?.type === 'stock_agent_completed' || Boolean(persisted),
                failed: latest?.type === 'stock_agent_failed',
            }
        })
    }, [liveEvents, results, runStatus])

    const [focusedRank, setFocusedRank] = useState<number | null>(null)

    // A new run invalidates the previous focus target.
    const runIdentity = runStatus?.request?.request_id || sessionAgents?.[0]?.symbol || 'current'
    useEffect(() => {
        setFocusedRank(null)
    }, [runIdentity])

    const active = slots.filter((slot) => slot.events.length > 0)
    const completed = slots.filter((slot) => slot.complete).length
    const failed = slots.filter((slot) => slot.failed).length

    // One agent and nothing to choose between: the workspace *is* the run.
    // No back control, because the only way out belongs to the caller.
    if (soloDirect && active.length === 1) {
        const solo = active[0]
        return (
            <AgentWorkspace slot={solo} result={results.find((item) => Number(item.rank) === solo.rank)} />
        )
    }

    const focused = slots.find((slot) => slot.rank === focusedRank)

    const roster = (
        <Panel aria-labelledby="agents-title" beam={stream === 'live' ? 'travel' : false}>
            <PanelHeader
                titleId="agents-title"
                label="Agent run"
                title={
                    active.length
                        ? `${count(active.length)} ${active.length === 1 ? 'agent' : 'agents'} in this run`
                        : 'Agents'
                }
                description={streamHint(stream)}
                actions={<StreamIndicator state={stream} />}
            />

            {active.length === 0 ? (
                <EmptyState
                    title={emptyState?.title || 'No agent activity'}
                    detail={
                        emptyState?.detail ||
                        'Agents appear here as soon as the scanner selects candidates. Monitoring runs continuously, so nothing needs to be started manually.'
                    }
                    minHeight={260}
                />
            ) : (
                <>
                    <AgentRoster slots={slots} onOpen={setFocusedRank} />
                    <div className="panel-footer flex flex-wrap items-center gap-x-5 gap-y-1 text-[10px] text-ink-tertiary">
                        <span>{completed} completed</span>
                        {failed > 0 && <span className="text-negative">{failed} failed</span>}
                        <span className="sm:ml-auto">Open an agent for its decision and full event log.</span>
                    </div>
                </>
            )}
        </Panel>
    )

    return (
        <PageSwitch
            page={focused ? 2 : 1}
            list={roster}
            detail={
                focused ? (
                    <AgentWorkspace
                        slot={focused}
                        result={results.find((item) => Number(item.rank) === focused.rank)}
                        onBack={() => setFocusedRank(null)}
                    />
                ) : null
            }
        />
    )
}
