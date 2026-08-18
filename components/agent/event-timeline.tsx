'use client'

import AgentMarkdown from '@/components/agent-markdown'
import { Shimmer } from '@/components/motion/shimmer'
import { SuccessCheck } from '@/components/motion/success-check'
import { ThinkingOrb } from '@/components/motion/thinking-orb'
import { cn } from '@/lib/cn'
import { formatTime } from '@/lib/format'
import { eventTitle, eventTone, TONE_DOT } from '@/components/ai-trading/utils'
import type { LiveAgentEvent } from '@/components/ai-trading/types'
import { AttachmentGallery } from './attachment-gallery'
import { DecisionPanel } from './decision-panel'
import { ClampedRegion, CodeBlock, Disclosure } from './disclosure'
import { ToolCallCard } from './tool-call-card'

/** Streamed prose above this length collapses by default. */
const CLAMP_THRESHOLD = 900

/**
 * The agent's event stream on a single rail.
 *
 * Each entry dispatches to the right renderer for its payload — markdown for
 * prose, `ToolCallCard` for tool traffic, `DecisionPanel` for decisions.
 *
 * Motion. Only the last event gets any, and only when it represents something
 * still in flight. That restraint is deliberate: this list can run to dozens of
 * entries, and animating each one as it arrives would turn a log into a
 * fairground. The events above the last are settled history and stay still.
 *
 *   - A trailing `thinking` or `response_delta` event is the agent mid-thought,
 *     so its title shimmers (recipe 15) and carries a `composing` orb.
 *   - A completion event draws a success check (recipe 10). This is the moment
 *     the run's outcome exists, and it is worth marking once.
 */
export function EventTimeline({ events }: { events: LiveAgentEvent[] }) {
    return (
        <ol className="event-timeline">
            {events.map((event, index) => {
                const tone = eventTone(event)
                const isToolCall = event.type.startsWith('stock_agent_tool_call_')
                const long = (event.message?.length || 0) > CLAMP_THRESHOLD
                // The report duplicates the message on completion events.
                const showReport = event.report_text && event.report_text !== event.message

                const isLast = index === events.length - 1
                const streaming =
                    isLast &&
                    (event.type === 'stock_agent_thinking' || event.type === 'stock_agent_response_delta')
                const completed = event.type === 'stock_agent_completed'

                return (
                    <li
                        key={`${event.type}-${event.sequence ?? index}-${event.sent_at_utc || index}`}
                        className="event-timeline-item"
                    >
                        <span aria-hidden className={cn('event-timeline-dot', TONE_DOT[tone])} />

                        <div className="flex items-baseline justify-between gap-3">
                            <p
                                className={cn(
                                    'flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em]',
                                    tone === 'negative'
                                        ? 'text-negative'
                                        : tone === 'positive'
                                          ? 'text-positive'
                                          : 'text-ink-secondary',
                                )}
                            >
                                {streaming ? (
                                    <>
                                        <ThinkingOrb state="composing" size={20} className="-my-1 text-ink-secondary" />
                                        <Shimmer>{eventTitle(event)}</Shimmer>
                                    </>
                                ) : (
                                    <>
                                        {completed && <SuccessCheck size={13} className="text-positive" />}
                                        {eventTitle(event)}
                                    </>
                                )}
                            </p>
                            <p className="nums flex-shrink-0 font-mono text-[9px] text-ink-tertiary">
                                {formatTime(event.sent_at_utc)}
                            </p>
                        </div>

                        <div className="mt-2.5 space-y-3">
                            {event.message &&
                                (long ? (
                                    <ClampedRegion>
                                        <AgentMarkdown>{event.message}</AgentMarkdown>
                                    </ClampedRegion>
                                ) : (
                                    <AgentMarkdown>{event.message}</AgentMarkdown>
                                ))}

                            {isToolCall && <ToolCallCard event={event} />}

                            {event.input && (
                                <Disclosure label="Structured input" hint={`${Object.keys(event.input).length} keys`}>
                                    <CodeBlock maxHeight={240}>{JSON.stringify(event.input, null, 2)}</CodeBlock>
                                </Disclosure>
                            )}

                            {event.decision && <DecisionPanel decision={event.decision} />}

                            {event.attachments && <AttachmentGallery attachments={event.attachments} />}

                            {showReport && (
                                <div className="border-t border-line pt-3">
                                    <ClampedRegion expandLabel="Show full report">
                                        <AgentMarkdown>{event.report_text}</AgentMarkdown>
                                    </ClampedRegion>
                                </div>
                            )}

                            {event.error && (
                                <div className="rounded-xl border border-danger/25 bg-danger/[0.05] p-3.5">
                                    <AgentMarkdown tone="danger">{event.error}</AgentMarkdown>
                                </div>
                            )}
                        </div>
                    </li>
                )
            })}
        </ol>
    )
}
