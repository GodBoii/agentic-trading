'use client'

import { useEffect, useMemo, useState } from 'react'
import { EmptyState } from '@/components/ui/empty-state'
import { Panel, PanelHeader } from '@/components/ui/panel'
import { count } from '@/lib/format'
import {
    agentDisplayName,
    agentSlotRanks,
    mergedEventsForRank,
} from '@/components/ai-trading/utils'
import type {
    AgentResult,
    AgentRunStatus,
    LiveAgentEvent,
    StreamState,
} from '@/components/ai-trading/types'
import { AgentRoster, type AgentSlot } from './agent-roster'
import { AgentWorkspace } from './agent-workspace'
import { StreamIndicator, streamHint } from './stream-indicator'

/**
 * Roster ⇄ workspace switch for a run, live or archived.
 *
 * Slot construction is delegated to `components/ai-trading/utils` — the page
 * previously carried its own duplicate copies of `mergedEventsForRank`,
 * `agentSlotRanks` and `coalesceAgentEvents` alongside the shared ones.
 */
export function AgentConsole({
    runStatus,
    liveEvents,
    sessionAgents,
    stream,
    emptyState,
}: {
    runStatus: AgentRunStatus | null
    liveEvents: Record<number, LiveAgentEvent[]>
    sessionAgents?: AgentResult[]
    stream: StreamState
    emptyState?: { title: string; detail: string }
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

    const focused = slots.find((slot) => slot.rank === focusedRank)
    if (focused) {
        return (
            <AgentWorkspace
                slot={focused}
                result={results.find((item) => Number(item.rank) === focused.rank)}
                onBack={() => setFocusedRank(null)}
            />
        )
    }

    const active = slots.filter((slot) => slot.events.length > 0)
    const completed = slots.filter((slot) => slot.complete).length
    const failed = slots.filter((slot) => slot.failed).length

    return (
        <Panel aria-labelledby="agents-title">
            <PanelHeader
                titleId="agents-title"
                label="Agent run"
                title={active.length ? `${count(active.length)} ${active.length === 1 ? 'agent' : 'agents'} in this run` : 'Agents'}
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
                        <span>
                            {completed} completed
                        </span>
                        {failed > 0 && <span className="text-negative">{failed} failed</span>}
                        <span className="ml-auto">Select an agent to open its decision, charts and full event log.</span>
                    </div>
                </>
            )}
        </Panel>
    )
}
