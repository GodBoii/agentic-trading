'use client'

import type { CSSProperties, ElementType, ReactNode } from 'react'
import { cn } from '@/lib/cn'

export type BeamTone = 'accent' | 'positive' | 'negative' | 'warning'
export type BeamMode = 'travel' | 'pulse'

const TONE_COLOR: Record<BeamTone, string> = {
    accent: 'var(--accent)',
    positive: 'var(--dash-positive)',
    negative: 'var(--dash-negative)',
    warning: 'var(--dash-warning)',
}

/**
 * Border beam — an animated edge for a surface that is genuinely active.
 *
 * `travel` runs a glow around the perimeter; `pulse` breathes the whole edge
 * without rotating. Travel draws the eye harder, so it is reserved for the one
 * surface that is live right now — a run in flight, a field awaiting input.
 * Pulse is the right choice when more than one surface needs emphasis, because
 * several traveling beams on screen compete with each other and with the data.
 *
 * The skill is explicit that animated borders should not be sprinkled across
 * many simultaneous elements, and that constraint is respected here by
 * gating on real state: the beam is only ever `on` while something is
 * actually happening.
 *
 * Implemented as a conic gradient clipped to a 1px frame with a mask
 * composite, rather than the React package the skill references — the effect
 * is wanted in two places, which does not justify a runtime dependency. The
 * beam layer is `pointer-events: none`, so it never interferes with the
 * content it wraps.
 */
export function BorderBeam({
    children,
    active = true,
    mode = 'travel',
    tone = 'accent',
    /** 0–1. Lower this when the beam sits next to dense figures. */
    strength = 1,
    /** Seconds per cycle. */
    duration,
    className,
    as: Tag = 'div',
}: {
    children: ReactNode
    active?: boolean
    mode?: BeamMode
    tone?: BeamTone
    strength?: number
    duration?: number
    className?: string
    as?: ElementType
}) {
    // Custom properties are not in the `CSSProperties` index, so the record is
    // built loosely and asserted once at the boundary.
    const style: Record<string, string> = {
        '--beam-color': TONE_COLOR[tone],
        '--beam-strength': String(Math.min(1, Math.max(0, strength))),
    }
    if (duration) style['--beam-dur'] = `${duration}s`

    return (
        <Tag
            className={cn('t-beam', className)}
            // `off` rather than removing the attribute, so the beam fades out
            // over 400ms instead of vanishing between frames.
            data-beam={active ? mode : 'off'}
            style={style as CSSProperties}
        >
            {children}
        </Tag>
    )
}
