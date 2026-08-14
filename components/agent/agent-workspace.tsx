'use client'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/ui/empty-state'
import { ArrowLeft } from '@/components/ui/icons'
import { Panel, PanelBody, PanelHeader } from '@/components/ui/panel'
import { count } from '@/lib/format'
import type { AgentResult } from '@/components/ai-trading/types'
import { AttachmentGallery } from './attachment-gallery'
import { DecisionPanel } from './decision-panel'
import { EventTimeline } from './event-timeline'
import { MilestoneTrack } from './milestone-track'
import { hasRunMetadata, RunMetadata } from './run-metadata'
import { slotState, type AgentSlot } from './agent-roster'

/**
 * One agent in full.
 *
 * Ordered conclusion → evidence → audit trail: the decision first, then the
 * charts it was made from, then the raw event log, then run accounting. The
 * previous layout opened with metadata and the chart rail, so the actual
 * decision sat below the fold under a wall of streamed text.
 */
export function AgentWorkspace({
    slot,
    result,
    onBack,
}: {
    slot: AgentSlot
    result?: AgentResult
    onBack: () => void
}) {
    const state = slotState(slot)
    const latest = slot.events[slot.events.length - 1]

    const decision = result?.decision || latest?.decision
    const attachments = result?.attachments || latest?.attachments
    const metadata = result?.agent_metadata || latest?.agent_metadata

    return (
        <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <Button size="sm" onClick={onBack}>
                    <ArrowLeft size={13} />
                    All agents
                </Button>
                <div className="flex items-center gap-2.5">
                    <span className="dash-label">Agent {slot.rank}</span>
                    <Badge tone={state.tone}>{state.label}</Badge>
                </div>
            </div>

            <Panel>
                <PanelHeader
                    label="Agent workspace"
                    title={slot.name}
                    actions={
                        <span className="nums font-mono text-[10px] text-ink-tertiary">
                            {count(slot.events.length)} events
                        </span>
                    }
                />
                <PanelBody>
                    <MilestoneTrack events={slot.events} />
                </PanelBody>
            </Panel>

            {decision && (
                <Panel aria-labelledby="agent-decision">
                    <PanelHeader titleId="agent-decision" label="Outcome" title="Decision" />
                    <PanelBody>
                        <DecisionPanel decision={decision} />
                    </PanelBody>
                </Panel>
            )}

            {attachments && (attachments.images?.length || attachments.files?.length) ? (
                <Panel aria-labelledby="agent-evidence">
                    <PanelHeader
                        titleId="agent-evidence"
                        label="Evidence"
                        title="Charts and artifacts"
                        description="Rendered by the backend at the moment the decision was taken."
                    />
                    <PanelBody>
                        <AttachmentGallery attachments={attachments} />
                    </PanelBody>
                </Panel>
            ) : null}

            <Panel aria-labelledby="agent-activity">
                <PanelHeader
                    titleId="agent-activity"
                    label="Audit trail"
                    title="Activity log"
                    description="Every event the agent emitted, in order."
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
