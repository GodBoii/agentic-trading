import { cn } from '@/lib/cn'
import { formatTime } from '@/lib/format'
import { agentMilestones } from '@/components/ai-trading/utils'
import type { LiveAgentEvent } from '@/components/ai-trading/types'

/**
 * The agent lifecycle as a stepper: Selected → Started → Charts ready →
 * Completed. Answers "how far did this get, and where did it stall" without
 * reading the event log, which is the first question on a run in flight.
 *
 * Motion. The dots and connectors tween their colour and the connector grows
 * from the left as a stage is reached. That is the whole point of a stepper on
 * a live run: the reader is watching for the next stage to land, and a stage
 * that simply changes colour between frames is easy to miss while looking
 * elsewhere on the page. Nothing moves once the run is settled.
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
                                        'h-2 w-2 flex-shrink-0 rounded-full transition-[background-color,border-color] duration-[350ms] ease-[cubic-bezier(0.22,1,0.36,1)]',
                                        milestone.failed
                                            ? 'bg-negative'
                                            : milestone.reached
                                              ? 'bg-positive'
                                              : 'border border-line-strong bg-transparent',
                                    )}
                                />
                                <span
                                    className={cn(
                                        'whitespace-nowrap text-[11px] transition-colors duration-[350ms] ease-[cubic-bezier(0.22,1,0.36,1)]',
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
                            // The connector fills from the left as the stage is
                            // reached, so progress reads as travelling forward
                            // rather than as segments lighting up at random.
                            <span
                                aria-hidden
                                className="relative mx-3 mt-[3px] h-px w-8 flex-shrink-0 bg-line sm:w-12"
                            >
                                <span
                                    className={cn(
                                        'absolute inset-y-0 left-0 bg-positive/40 transition-[width] duration-[500ms] ease-[cubic-bezier(0.22,1,0.36,1)]',
                                        milestone.reached ? 'w-full' : 'w-0',
                                    )}
                                />
                            </span>
                        )}
                    </li>
                )
            })}
        </ol>
    )
}
