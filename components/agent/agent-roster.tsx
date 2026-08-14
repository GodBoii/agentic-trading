'use client'

import { Badge, type Tone } from '@/components/ui/badge'
import { ArrowRight } from '@/components/ui/icons'
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
 * Replaces a horizontal scroll rail of fixed 220px cards — with four or five
 * agents, most of the run was off-screen behind a scroll gesture. Each card
 * carries the progress count and last activity so triage does not require
 * opening every slot.
 */
export function AgentRoster({ slots, onOpen }: { slots: AgentSlot[]; onOpen: (rank: number) => void }) {
    return (
        // Flush: this always sits between a Panel's header and footer, so it
        // must not draw its own frame.
        <ul className="cell-grid cell-grid-flush grid-cols-1 sm:grid-cols-2 xl:grid-cols-3">
            {slots.map((slot) => {
                const state = slotState(slot)
                const latest = slot.events[slot.events.length - 1]
                const milestones = agentMilestones(slot.events)
                const reached = milestones.filter((milestone) => milestone.reached).length

                return (
                    <li key={slot.rank}>
                        <button
                            type="button"
                            onClick={() => onOpen(slot.rank)}
                            className="card-button group h-full p-4"
                            aria-label={`Open ${slot.name}, ${state.label}`}
                        >
                            <div className="flex items-center justify-between gap-3">
                                <span className="dash-label">Agent {slot.rank}</span>
                                <Badge tone={state.tone} size="sm">
                                    {state.label}
                                </Badge>
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

                            {/* Milestone progress as ticks — compact enough for a card. */}
                            <div aria-hidden className="mt-4 flex gap-1">
                                {milestones.map((milestone) => (
                                    <span
                                        key={milestone.key}
                                        className={cn(
                                            'h-[3px] flex-1 rounded-full',
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
                                <ArrowRight
                                    size={14}
                                    className="text-ink-tertiary transition-transform duration-150 group-hover:translate-x-0.5 group-hover:text-ink-secondary"
                                />
                            </div>
                        </button>
                    </li>
                )
            })}
        </ul>
    )
}
