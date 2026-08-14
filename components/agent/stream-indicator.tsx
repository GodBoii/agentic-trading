import { StatusChip, type Tone } from '@/components/ui/badge'
import type { StreamState } from '@/components/ai-trading/types'

const STREAM_META: Record<StreamState, { tone: Tone; label: string; pulse?: boolean; hint: string }> = {
    live: { tone: 'positive', label: 'Live', hint: 'Streaming agent events in real time.' },
    connecting: { tone: 'warning', label: 'Connecting', pulse: true, hint: 'Opening the event stream.' },
    reconnecting: { tone: 'warning', label: 'Reconnecting', pulse: true, hint: 'The stream dropped and is retrying.' },
    fallback: { tone: 'warning', label: 'Polling', hint: 'Streaming is unavailable; status is being polled instead.' },
    unavailable: { tone: 'negative', label: 'Stream offline', hint: 'Live events are unavailable. Status still refreshes periodically.' },
    paused: { tone: 'neutral', label: 'Paused', hint: 'Not subscribed while viewing another section.' },
    archive: { tone: 'neutral', label: 'Archived', hint: 'Replayed from a saved run.' },
}

/**
 * Stream health, with the consequence spelled out in the tooltip.
 *
 * The previous indicator did `connectionState.includes('live')` against a bare
 * string, so `fallback`, `reconnecting` and `unavailable` all rendered
 * identically as a generic amber dot.
 */
export function StreamIndicator({ state }: { state: StreamState }) {
    const meta = STREAM_META[state]
    return (
        <span title={meta.hint}>
            <StatusChip tone={meta.tone} pulse={meta.pulse}>
                {meta.label}
            </StatusChip>
        </span>
    )
}

export function streamHint(state: StreamState) {
    return STREAM_META[state].hint
}
