'use client'

import { Badge, type Tone } from '@/components/ui/badge'
import { Shimmer } from '@/components/motion/shimmer'
import { ThinkingOrb } from '@/components/motion/thinking-orb'
import { formatCharCount, formatDuration } from '@/lib/format'
import type { LiveAgentEvent } from '@/components/ai-trading/types'
import { CodeBlock, Disclosure } from './disclosure'

type ToolOutcome = 'running' | 'succeeded' | 'partial' | 'failed'

const OUTCOME_TONE: Record<ToolOutcome, Tone> = {
    running: 'accent',
    succeeded: 'positive',
    partial: 'warning',
    failed: 'negative',
}

function outcomeOf(event: LiveAgentEvent): ToolOutcome {
    if (event.type === 'stock_agent_tool_call_error') return 'failed'
    if (event.type === 'stock_agent_tool_call_completed') return event.result_partial ? 'partial' : 'succeeded'
    return 'running'
}

/**
 * One tool invocation: outcome, cost, and its payloads behind disclosures.
 *
 * Duration and result size are shown up front because they are what makes a
 * tool call actionable — a 40-second call or a truncated result is the signal
 * worth noticing.
 *
 * Motion. A running call previously showed a bare spinner beside a badge
 * reading "running". It now pairs a thinking orb with a shimmering label, and
 * the distinction is worth the change: a tool call is where an agent spends
 * most of its wall-clock time, so this indicator is on screen longer than any
 * other in the app. A spinner beside the word "running" says the same thing
 * twice and neither part says whether progress is being made; a live label
 * reads as the system still working.
 *
 * `searching` is the honest state name here — the agent is out fetching
 * something and waiting on it.
 */
export function ToolCallCard({ event }: { event: LiveAgentEvent }) {
    const outcome = outcomeOf(event)
    const argCount = event.tool_args ? Object.keys(event.tool_args).length : 0
    const result = event.result || event.result_preview
    const running = outcome === 'running'

    return (
        <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                {running ? (
                    <span className="flex items-center gap-2">
                        <ThinkingOrb state="searching" size={20} className="text-accent" />
                        <Shimmer className="font-mono text-[10px] uppercase tracking-[0.08em]">Running</Shimmer>
                    </span>
                ) : (
                    <Badge tone={OUTCOME_TONE[outcome]}>{outcome}</Badge>
                )}

                {event.duration_seconds !== undefined && (
                    <span className="nums font-mono text-[10px] text-ink-secondary">
                        {formatDuration(event.duration_seconds)}
                    </span>
                )}
                {event.result_length !== undefined && (
                    <span className="nums font-mono text-[10px] text-ink-tertiary">
                        {formatCharCount(event.result_length)}
                    </span>
                )}
                {event.result_partial && (
                    <span className="text-[10px] text-warning">Result truncated by the backend</span>
                )}
            </div>

            {argCount > 0 && (
                <Disclosure label="Arguments" hint={`${argCount} ${argCount === 1 ? 'key' : 'keys'}`}>
                    <CodeBlock maxHeight={200}>{JSON.stringify(event.tool_args, null, 2)}</CodeBlock>
                </Disclosure>
            )}

            {result && (
                <Disclosure
                    label={event.result ? 'Tool result' : 'Result preview'}
                    hint={formatCharCount(event.result_length ?? result.length)}
                    // A failure is the reason the reader is here; open it.
                    defaultOpen={outcome === 'failed'}
                >
                    <CodeBlock>{result}</CodeBlock>
                </Disclosure>
            )}
        </div>
    )
}
