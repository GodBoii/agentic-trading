'use client'

import { StatusChip, type Tone } from '@/components/ui/badge'
import { Tooltip } from '@/components/motion/tooltip'
import { ThinkingOrb, type OrbState } from '@/components/motion/thinking-orb'
import type { StreamState } from '@/components/ai-trading/types'

/**
 * Stream health, with the consequence spelled out.
 *
 * `orb` is set only for the states where the client is actively doing
 * something a reader benefits from seeing — opening or retrying a connection.
 * A settled stream (`live`, `paused`, `archive`) or a dead one
 * (`unavailable`) gets a static dot: an animated indicator on a state that
 * is not changing is decoration, which the motion system explicitly rules
 * out.
 */
const STREAM_META: Record<
    StreamState,
    { tone: Tone; label: string; pulse?: boolean; orb?: OrbState; hint: string }
> = {
    live: {
        tone: 'positive',
        label: 'Live',
        pulse: true,
        hint: 'Streaming agent events in real time.',
    },
    connecting: {
        tone: 'warning',
        label: 'Connecting',
        orb: 'working',
        hint: 'Opening the event stream.',
    },
    reconnecting: {
        tone: 'warning',
        label: 'Reconnecting',
        orb: 'searching',
        hint: 'The stream dropped and is retrying.',
    },
    fallback: {
        tone: 'warning',
        label: 'Polling',
        pulse: true,
        hint: 'Streaming is unavailable; status is being polled instead.',
    },
    unavailable: {
        tone: 'negative',
        label: 'Stream offline',
        hint: 'Live events are unavailable. Status still refreshes periodically.',
    },
    paused: { tone: 'neutral', label: 'Paused', hint: 'Not subscribed while viewing another section.' },
    archive: { tone: 'neutral', label: 'Archived', hint: 'Replayed from a saved run.' },
}

/**
 * Stream health chip.
 *
 * The hint moves from a `title` attribute to a real tooltip (recipe 17). That
 * is a functional fix as much as a visual one: a native `title` never appears
 * for keyboard users and is invisible on touch, so the explanation of *what a
 * degraded stream means for you* was unreachable for anyone not hovering a
 * mouse. The tooltip waits 80ms before appearing so a passing cursor does not
 * trigger it, and dismisses instantly.
 */
export function StreamIndicator({ state }: { state: StreamState }) {
    const meta = STREAM_META[state]

    return (
        <Tooltip label={meta.hint} align="end">
            {meta.orb ? (
                <span className="product-chip">
                    <ThinkingOrb state={meta.orb} size={20} className="-my-0.5 -ml-0.5 text-warning" />
                    {meta.label}
                </span>
            ) : (
                <StatusChip tone={meta.tone} pulse={meta.pulse}>
                    {meta.label}
                </StatusChip>
            )}
        </Tooltip>
    )
}

export function streamHint(state: StreamState) {
    return STREAM_META[state].hint
}
