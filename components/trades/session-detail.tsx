'use client'

import { AgentConsole } from '@/components/agent/agent-console'
import type { TradeSession } from '@/components/ai-trading/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ArrowLeft } from '@/components/ui/icons'
import { CellGrid, Panel, PanelHeader } from '@/components/ui/panel'
import { Tooltip } from '@/components/motion/tooltip'
import { count, formatDateTime } from '@/lib/format'
import { sessionStatusTone } from './utils'

/**
 * One archived run, reusing the live Agent console.
 *
 * The sessions API synthesizes a `status_snapshot` in the same shape the live
 * stream produces, so history and live runs render through identical components
 * — an archived decision is presented exactly as it was when it was made.
 *
 * Motion. The entrance belongs to the parent: the Trades page slides this in
 * from the right as the archive exits left. Nothing here stages its own arrival,
 * because two entrances on one navigation read as a stutter.
 *
 * The run reference gets a tooltip rather than a `title` attribute — it is
 * truncated, so without one the full identifier was unreachable for keyboard
 * and touch users.
 */
export function SessionDetail({ session, onBack }: { session: TradeSession; onBack: () => void }) {
    const agents = session.agents || []
    const updatedAt = session.updated_at_utc || session.created_at_utc
    const executed = session.summary?.executed_count

    return (
        <div className="space-y-4">
            <Button size="sm" onClick={onBack}>
                <ArrowLeft size={13} />
                All runs
            </Button>

            <Panel aria-labelledby="session-title">
                <PanelHeader
                    titleId="session-title"
                    label="Archived run"
                    title={session.title}
                    actions={<Badge tone={sessionStatusTone(session.status)}>{session.status}</Badge>}
                />
                <CellGrid flush className="grid-cols-2 lg:grid-cols-4">
                    <Cell label="Agents" value={count(agents.length)} />
                    <Cell
                        label="Orders placed"
                        value={executed === undefined || executed === null ? 'Not recorded' : count(Number(executed))}
                    />
                    <Cell label="Last updated" value={formatDateTime(updatedAt)} />
                    <Cell label="Run reference" value={session.request_id || session.session_id} mono truncate />
                </CellGrid>
            </Panel>

            <AgentConsole
                runStatus={session.status_snapshot || null}
                liveEvents={{}}
                sessionAgents={agents}
                stream="archive"
                emptyState={{
                    title: 'No agent output saved',
                    detail: 'This run was archived without per-agent results. It may have ended before any agent started.',
                }}
            />
        </div>
    )
}

function Cell({
    label,
    value,
    mono,
    truncate,
}: {
    label: string
    value: string
    mono?: boolean
    truncate?: boolean
}) {
    const body = (
        <p
            className={`text-[12px] text-ink-primary ${mono ? 'nums font-mono text-[11px]' : ''} ${truncate ? 'truncate' : ''}`}
        >
            {value}
        </p>
    )

    return (
        <div className="min-w-0 px-4 py-3.5">
            <p className="dash-label mb-1.5">{label}</p>
            {truncate ? (
                <Tooltip label={value} align="end">
                    {body}
                </Tooltip>
            ) : (
                body
            )}
        </div>
    )
}
