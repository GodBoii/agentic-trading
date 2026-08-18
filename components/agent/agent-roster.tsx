'use client'

import { Badge, type Tone } from '@/components/ui/badge'
import { LearnMoreChevron } from '@/components/motion/learn-more'
import { ThinkingOrb } from '@/components/motion/thinking-orb'
import { useHoverGroup } from '@/components/motion/hover-group'
import { cn } from '@/lib/cn'
import { formatTime } from '@/lib/format'
import { agentMilestones, eventTitle } from '@/components/ai-trading/utils'
import type { LiveAgentEvent } from '@/components/ai-trading/types'

export interface AgentSlot {
    rank: number
    name: string
    events: LiveAgentEvent[]
    complete: boolean
    failed: boolean
}

/** Derive a slot's headline state from its event stream. */
export function slotState(slot: AgentSlot): { tone: Tone; label: string } {
    if (slot.failed) return { tone: 'negative', label: 'Failed' }
    if (slot.complete) return { tone: 'positive', label: 'Completed' }
    if (slot.events.length) return { tone: 'warning', label: 'Running' }
    return { tone: 'neutral', label: 'Queued' }
}

/**
 * The agents in a run, as a grid of cards.
 *
 * Each card carries its progress count and last activity, so triage does not
 * require opening every slot.
 *
 * Motion. Three recipes, each tied to something real about this surface:
 *
 *   - Hover group (recipe 11). Hovering one card lifts it and lifts its
 *     neighbours by a power falloff, then springs the row back on leave. The
 *     agents in a run are peers working the same request, and the falloff
 *     signals that they belong to one group rather than being independent
 *     tiles. The return uses the bouncier curve — this is the one place the
 *     hover-out is more elaborate than the hover-in.
 *
 *   - Thinking orb, for a slot that is still running. It replaces a static
 *     amber badge with an indicator that says the agent is working, which on a
 *     card that may sit mid-run for forty seconds is the difference between
 *     "in progress" and "possibly stuck".
 *
 *   - Learn-more chevron (recipe 24). The arms open into an arrow on hover,
 *     replacing a `translate-x-0.5` nudge on a static glyph.
 *
 * The milestone ticks animate their fill so a stage completing mid-hover is
 * visible without the card being reopened.
 */
export function AgentRoster({ slots, onOpen }: { slots: AgentSlot[]; onOpen: (rank: number) => void }) {
    const { groupProps, itemProps } = useHoverGroup<HTMLUListElement>()

    return (
        // Flush: this always sits between a Panel's header and footer, so it
        // must not draw its own frame.
        <ul
            {...groupProps}
            className="cell-grid cell-grid-flush grid-cols-1 sm:grid-cols-2 xl:grid-cols-3"
        >
            {slots.map((slot, index) => {
                const state = slotState(slot)
                const latest = slot.events[slot.events.length - 1]
                const milestones = agentMilestones(slot.events)
                const reached = milestones.filter((milestone) => milestone.reached).length
                const running = !slot.complete && !slot.failed && slot.events.length > 0

                const { className: itemClass, ...itemHandlers } = itemProps(index)

                return (
                    <li key={slot.rank} className={itemClass} {...itemHandlers}>
                        <button
                            type="button"
                            onClick={() => onOpen(slot.rank)}
                            className="card-button group h-full p-4"
                            aria-label={`Open ${slot.name}, ${state.label}`}
                        >
                            <div className="flex items-center justify-between gap-3">
                                <span className="dash-label">Agent {slot.rank}</span>
                                <span className="flex items-center gap-2">
                                    {running && <ThinkingOrb state="working" size={20} className="text-warning" />}
                                    <Badge tone={state.tone} size="sm">
                                        {state.label}
                                    </Badge>
                                </span>
                            </div>

                            <p className="mt-4 truncate text-[15px] font-medium tracking-[-0.02em] text-ink-primary">
                                {slot.name}
                            </p>
                            <p className="mt-1 truncate text-[11px] text-ink-tertiary">
                                {latest ? eventTitle(latest) : 'Waiting for assignment'}
                                {latest?.sent_at_utc && (
                                    <span className="nums font-mono"> · {formatTime(latest.sent_at_utc)}</span>
                                )}
                            </p>

                            {/* Milestone progress as ticks — compact enough for a card.
                                The colour tweens so a stage completing while the card
                                is on screen is visible without reopening it. */}
                            <div aria-hidden className="mt-4 flex gap-1">
                                {milestones.map((milestone) => (
                                    <span
                                        key={milestone.key}
                                        className={cn(
                                            'h-[3px] flex-1 rounded-full transition-colors duration-[350ms] ease-[cubic-bezier(0.22,1,0.36,1)]',
                                            milestone.failed
                                                ? 'bg-negative'
                                                : milestone.reached
                                                  ? 'bg-positive'
                                                  : 'bg-white/[0.08]',
                                        )}
                                    />
                                ))}
                            </div>

                            <div className="mt-3 flex items-center justify-between border-t border-line pt-3">
                                <span className="nums font-mono text-[9px] uppercase tracking-[0.12em] text-ink-tertiary">
                                    {reached}/{milestones.length} stages · {slot.events.length} events
                                </span>
                                <span className="text-ink-tertiary transition-colors duration-[250ms] group-hover:text-ink-secondary">
                                    <LearnMoreChevron size={14} />
                                </span>
                            </div>
                        </button>
                    </li>
                )
            })}
        </ul>
    )
}
