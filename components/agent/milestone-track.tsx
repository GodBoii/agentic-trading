import { cn } from '@/lib/cn'
import { formatTime } from '@/lib/format'
import { agentMilestones } from '@/components/ai-trading/utils'
import type { LiveAgentEvent } from '@/components/ai-trading/types'

/**
 * The agent lifecycle as a stepper: Selected → Started → Charts ready →
 * Completed. Answers "how far did this get, and where did it stall" without
 * reading the event log, which is the first question on a run in flight.
 */
export function MilestoneTrack({ events, className }: { events: LiveAgentEvent[]; className?: string }) {
    const milestones = agentMilestones(events)

    return (
        <ol className={cn('flex flex-wrap items-start gap-y-3', className)}>
            {milestones.map((milestone, index) => {
                const last = index === milestones.length - 1
                return (
                    <li key={milestone.key} className="flex min-w-0 items-start">
                        <div className="flex min-w-0 flex-col gap-1">
                            <div className="flex items-center gap-2">
                                <span
                                    aria-hidden
                                    className={cn(
                                        'h-2 w-2 flex-shrink-0 rounded-full',
                                        milestone.failed
                                            ? 'bg-negative'
                                            : milestone.reached
                                              ? 'bg-positive'
                                              : 'border border-line-strong bg-transparent',
                                    )}
                                />
                                <span
                                    className={cn(
                                        'whitespace-nowrap text-[11px]',
                                        milestone.failed
                                            ? 'text-negative'
                                            : milestone.reached
                                              ? 'text-ink-primary'
                                              : 'text-ink-tertiary',
                                    )}
                                >
                                    {milestone.label}
                                </span>
                            </div>
                            <span className="nums pl-4 font-mono text-[9px] text-ink-tertiary">
                                {milestone.at ? formatTime(milestone.at) : '—'}
                            </span>
                        </div>
                        {!last && (
                            <span
                                aria-hidden
                                className={cn(
                                    'mx-3 mt-[3px] h-px w-8 flex-shrink-0 sm:w-12',
                                    milestone.reached ? 'bg-positive/30' : 'bg-line',
                                )}
                            />
                        )}
                    </li>
                )
            })}
        </ol>
    )
}
