'use client'

import type { ReactNode } from 'react'
import { Badge, type Tone } from '@/components/ui/badge'
import { CellGrid } from '@/components/ui/panel'
import { Notice } from '@/components/ui/notice'
import { NumberFlow } from '@/components/motion/number-flow'
import { Shimmer } from '@/components/motion/shimmer'
import { TextSwap } from '@/components/motion/text-swap'
import { ThinkingOrb } from '@/components/motion/thinking-orb'
import { Tooltip } from '@/components/motion/tooltip'
import { formatElapsed, formatTime, humanizeKey } from '@/lib/format'
import type { AgentRunStatus } from '@/components/ai-trading/types'

const STATUS_TONE: Record<string, Tone> = {
    running: 'warning',
    completed: 'positive',
    failed: 'negative',
    error: 'negative',
    stale: 'warning',
    idle: 'neutral',
}

/**
 * Header strip for the current run: what it is, where it got to, and when it
 * last moved.
 *
 * `stale` is a real backend state — the API downgrades a `running` status that
 * has not been updated within its TTL — so it is surfaced with its own tone and
 * explanation rather than being displayed as if the run were still healthy.
 *
 * Motion. Each cell earns its treatment from what it reports:
 *
 *   - A `running` status gets an orb and a shimmering label. Its whole purpose
 *     is to say the run has not stopped, and a static amber badge cannot
 *     distinguish "running" from "stuck at running".
 *   - The current stage swaps in place when it advances (recipe 04) — this is a
 *     label reflecting a state change, which is exactly what the text swap is
 *     for.
 *   - The last-update clock re-enters on change (recipe 02). It ticks on every
 *     poll, and the pop-in is what makes "the run is alive" visible.
 *   - The request id gets a tooltip instead of a `title`, since it is truncated
 *     and was otherwise unreadable without a mouse.
 */
export function RunSummary({ status }: { status: AgentRunStatus | null }) {
    const state = status?.status || 'idle'
    const requestId = status?.request?.request_id
    const updatedAt = status?.updated_at_utc
    const running = state === 'running'

    return (
        <div className="space-y-3">
            <CellGrid className="grid-cols-2 lg:grid-cols-4">
                <Cell label="Run status">
                    {running ? (
                        <span className="flex items-center gap-2">
                            <ThinkingOrb state="working" size={20} className="-my-1 text-warning" />
                            <Shimmer className="text-[12px]">Running</Shimmer>
                        </span>
                    ) : (
                        <Badge tone={STATUS_TONE[state] || 'neutral'}>{state}</Badge>
                    )}
                </Cell>
                <Cell label="Current stage">
                    <StageLabel stage={status?.current_stage} />
                </Cell>
                <Cell label="Last update">
                    <span className="nums font-mono text-[12px] text-ink-primary">
                        {updatedAt ? <NumberFlow value={formatTime(updatedAt)} /> : '—'}
                    </span>
                    {updatedAt && (
                        <span className="mt-0.5 block font-mono text-[9px] text-ink-tertiary">
                            {formatElapsed(updatedAt)}
                        </span>
                    )}
                </Cell>
                <Cell label="Request">
                    {requestId ? (
                        <Tooltip label={requestId} align="end">
                            <span className="block max-w-full truncate font-mono text-[11px] text-ink-secondary">
                                {requestId}
                            </span>
                        </Tooltip>
                    ) : (
                        <span className="font-mono text-[11px] text-ink-tertiary">Not assigned</span>
                    )}
                </Cell>
            </CellGrid>

            {status?.message && <Notice tone="warning">{status.message}</Notice>}
            {status?.error && <Notice tone="danger">{status.error}</Notice>}
        </div>
    )
}

/**
 * The stage name swaps in place as the run advances (recipe 04). Split into its
 * own component so the swapping node keeps a stable identity across parent
 * re-renders — remounting it would reset the animation before it could play.
 */
function StageLabel({ stage }: { stage?: string }) {
    return (
        <TextSwap className="text-[12px] text-ink-primary">
            {stage ? humanizeKey(stage) : '—'}
        </TextSwap>
    )
}

function Cell({ label, children }: { label: string; children: ReactNode }) {
    return (
        <div className="min-w-0 px-4 py-3.5">
            <p className="dash-label mb-2">{label}</p>
            {children}
        </div>
    )
}
