'use client'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/ui/empty-state'
import { ArrowLeft } from '@/components/ui/icons'
import { Panel, PanelBody, PanelHeader } from '@/components/ui/panel'
import { ThinkingOrb } from '@/components/motion/thinking-orb'
import { count } from '@/lib/format'
import { hasLifecycleEvents } from '@/components/ai-trading/utils'
import type { AgentResult } from '@/components/ai-trading/types'
import { DecisionPanel } from './decision-panel'
import { EventTimeline } from './event-timeline'
import { MilestoneTrack } from './milestone-track'
import { hasRunMetadata, RunMetadata } from './run-metadata'
import { slotState, type AgentSlot } from './agent-roster'

/**
 * One agent in full: decision, then the audit trail, then run accounting.
 *
 * There used to be a "Charts and artifacts" panel between the decision and the
 * log. It is gone because it was the same gallery twice on one screen: the
 * events that carry attachments — `charts_ready` live, the synthesized
 * `completed` event on an archived run — already render `AttachmentGallery`
 * inside the timeline, at the point in the run where the charts were produced.
 * The standalone panel showed the identical images with no extra context, above
 * a log that repeated them a screen later.
 *
 * The lifecycle stepper only renders when the stream actually recorded a
 * lifecycle. A run replayed from `agno_sessions` has one synthesized completion
 * event and nothing else, so the stepper read "1/4 stages" on work that
 * finished cleanly — a progress bar reporting failure to progress.
 *
 * `onBack` is optional. When the caller opened this workspace directly, without
 * a roster to return to, it owns the way out and a second back button here would
 * be a control that leaves the reader on the same screen.
 *
 * Motion. The entrance is owned by the parent — `AgentConsole` slides this in
 * from the right as the roster exits left, so nothing here stages its own
 * arrival. Adding a second entrance on top would double-animate the same
 * navigation.
 *
 * The one indicator that belongs to this component is the orb beside the
 * workspace title while the agent is still running: on a screen the reader may
 * sit on for a minute waiting for a decision, "still working" is the most
 * useful thing the header can say.
 */
export function AgentWorkspace({
    slot,
    result,
    onBack,
}: {
    slot: AgentSlot
    result?: AgentResult
    onBack?: () => void
}) {
    const state = slotState(slot)
    const latest = slot.events[slot.events.length - 1]
    const running = !slot.complete && !slot.failed && slot.events.length > 0

    const decision = result?.decision || latest?.decision
    const metadata = result?.agent_metadata || latest?.agent_metadata
    const showLifecycle = hasLifecycleEvents(slot.events)

    return (
        <div className="space-y-4">
            {onBack && (
                <Button size="sm" onClick={onBack}>
                    <ArrowLeft size={13} />
                    All agents
                </Button>
            )}

            <Panel aria-labelledby="agent-workspace">
                <PanelHeader
                    titleId="agent-workspace"
                    label={`Agent ${slot.rank}`}
                    title={slot.name}
                    actions={
                        <span className="flex items-center gap-2.5">
                            {running && <ThinkingOrb state="working" size={20} className="text-warning" />}
                            <Badge tone={state.tone}>{state.label}</Badge>
                        </span>
                    }
                />
                {showLifecycle && (
                    <PanelBody>
                        <MilestoneTrack events={slot.events} />
                    </PanelBody>
                )}
            </Panel>

            {decision && (
                <Panel aria-labelledby="agent-decision">
                    <PanelHeader titleId="agent-decision" label="Outcome" title="Decision" />
                    <PanelBody>
                        <DecisionPanel decision={decision} />
                    </PanelBody>
                </Panel>
            )}

            <Panel aria-labelledby="agent-activity">
                <PanelHeader
                    titleId="agent-activity"
                    label="Audit trail"
                    title="Activity log"
                    description="Every event the agent emitted, in order, with the charts it read."
                    actions={
                        <span className="nums font-mono text-[10px] text-ink-tertiary">
                            {count(slot.events.length)} {slot.events.length === 1 ? 'event' : 'events'}
                        </span>
                    }
                />
                {slot.events.length ? (
                    <PanelBody>
                        <EventTimeline events={slot.events} />
                    </PanelBody>
                ) : (
                    <EmptyState
                        title="No events yet"
                        detail="This agent has been assigned but has not started emitting output."
                        minHeight={220}
                    />
                )}
            </Panel>

            {hasRunMetadata(metadata) && (
                <Panel aria-labelledby="agent-metadata">
                    <PanelHeader titleId="agent-metadata" label="Diagnostics" title="Run metadata" />
                    <PanelBody>
                        <RunMetadata metadata={metadata} />
                    </PanelBody>
                </Panel>
            )}
        </div>
    )
}
