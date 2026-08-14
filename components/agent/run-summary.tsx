import type { ReactNode } from 'react'
import { Badge, type Tone } from '@/components/ui/badge'
import { CellGrid } from '@/components/ui/panel'
import { Notice } from '@/components/ui/notice'
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
 */
export function RunSummary({ status }: { status: AgentRunStatus | null }) {
    const state = status?.status || 'idle'
    const requestId = status?.request?.request_id
    const updatedAt = status?.updated_at_utc

    return (
        <div className="space-y-3">
            <CellGrid className="grid-cols-2 lg:grid-cols-4">
                <Cell label="Run status">
                    <Badge tone={STATUS_TONE[state] || 'neutral'}>{state}</Badge>
                </Cell>
                <Cell label="Current stage">
                    <span className="text-[12px] text-ink-primary">
                        {status?.current_stage ? humanizeKey(status.current_stage) : '—'}
                    </span>
                </Cell>
                <Cell label="Last update">
                    <span className="nums font-mono text-[12px] text-ink-primary">
                        {updatedAt ? formatTime(updatedAt) : '—'}
                    </span>
                    {updatedAt && (
                        <span className="mt-0.5 block font-mono text-[9px] text-ink-tertiary">
                            {formatElapsed(updatedAt)}
                        </span>
                    )}
                </Cell>
                <Cell label="Request">
                    <span
                        className="block truncate font-mono text-[11px] text-ink-secondary"
                        title={requestId || undefined}
                    >
                        {requestId || 'Not assigned'}
                    </span>
                </Cell>
            </CellGrid>

            {status?.message && <Notice tone="warning">{status.message}</Notice>}
            {status?.error && <Notice tone="danger">{status.error}</Notice>}
        </div>
    )
}

function Cell({ label, children }: { label: string; children: ReactNode }) {
    return (
        <div className="px-4 py-3.5">
            <p className="dash-label mb-2">{label}</p>
            {children}
        </div>
    )
}
