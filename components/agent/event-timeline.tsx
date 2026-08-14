'use client'

import AgentMarkdown from '@/components/agent-markdown'
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
 * prose, `ToolCallCard` for tool traffic, `DecisionPanel` for decisions — rather
 * than the previous approach of rendering every event with the same card and
 * stringifying whatever it contained.
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

                return (
                    <li key={`${event.type}-${event.sequence ?? index}-${event.sent_at_utc || index}`} className="event-timeline-item">
                        <span aria-hidden className={cn('event-timeline-dot', TONE_DOT[tone])} />

                        <div className="flex items-baseline justify-between gap-3">
                            <p
                                className={cn(
                                    'font-mono text-[10px] uppercase tracking-[0.14em]',
                                    tone === 'negative' ? 'text-negative' : tone === 'positive' ? 'text-positive' : 'text-ink-secondary',
                                )}
                            >
                                {eventTitle(event)}
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
