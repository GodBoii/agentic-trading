'use client'

import { useMemo } from 'react'
import { cn } from '@/lib/cn'

/**
 * Thinking orb — semantic agent activity.
 *
 * Six states, each with its own motion, so the indicator says *what* the
 * agent is doing rather than only that it is busy. That distinction is the
 * whole justification for using one at all: on a screen where an agent may
 * spend forty seconds inside a single tool call, "searching" versus "solving"
 * is real information, and a generic spinner throws it away.
 *
 * The motion skill points at a canvas package for this role. This is a native
 * implementation instead: dots are plain elements placed on rings by angle and
 * radius, and CSS animates them. It costs no runtime dependency, no canvas
 * context, and no device-pixel-ratio handling, and it inherits `currentColor`
 * so it tones itself from whatever it sits inside.
 *
 * Two tuned sizes rather than one scaled design — 20px inline beside a label,
 * 64px as a standalone status. Each carries its own dot count and radii,
 * because a 20px orb with a 64px orb's dot count is just a grey disc.
 */
export type OrbState = 'working' | 'searching' | 'solving' | 'listening' | 'composing' | 'shaping'

const DEFAULT_LABEL: Record<OrbState, string> = {
    working: 'Working',
    searching: 'Searching',
    solving: 'Solving',
    listening: 'Listening',
    composing: 'Composing',
    shaping: 'Shaping',
}

/** Per-size tuning: ring radii as a fraction of the box, and dots per ring. */
const PRESETS = {
    20: { dot: 1.7, rings: [0.5, 0.34, 0.17], counts: [14, 10, 6] },
    64: { dot: 2.6, rings: [0.46, 0.33, 0.19], counts: [26, 18, 10] },
} as const

export function ThinkingOrb({
    state = 'working',
    size = 20,
    speed = 1,
    label,
    className,
}: {
    state?: OrbState
    /** 20 for inline use, 64 for a standalone indicator. */
    size?: 20 | 64
    /** Multiplier on the baked speed. Above ~1.5 reads as agitated. */
    speed?: number
    label?: string
    className?: string
}) {
    const preset = PRESETS[size]

    // Positions are deterministic, so they are computed once per size rather
    // than on every render of a component that lives inside a live event feed.
    const rings = useMemo(
        () =>
            preset.rings.map((fraction, ringIndex) => {
                const count = preset.counts[ringIndex]
                const radius = fraction * size
                return Array.from({ length: count }, (_, dotIndex) => ({
                    angle: (dotIndex / count) * 360,
                    radius,
                    // 0..1 around the ring, used as a delay fraction so a
                    // sweep travels instead of every dot pulsing at once.
                    phase: dotIndex / count,
                }))
            }),
        [preset, size],
    )

    return (
        <span
            role="img"
            aria-label={label || DEFAULT_LABEL[state]}
            data-state={state}
            className={cn('t-orb', className)}
            style={{
                width: size,
                height: size,
                // Speed is inverted: a higher multiplier means shorter cycles.
                ['--orb-speed' as string]: String(1 / Math.max(0.1, speed)),
                ['--orb-dot' as string]: `${preset.dot}px`,
            }}
        >
            {rings.map((dots, ringIndex) => (
                <span className="t-orb-ring" key={ringIndex}>
                    {dots.map((dot, dotIndex) => (
                        <i
                            key={dotIndex}
                            style={{
                                ['--a' as string]: `${dot.angle}deg`,
                                ['--r' as string]: `${dot.radius}px`,
                                ['--d' as string]: dot.phase.toFixed(3),
                            }}
                        />
                    ))}
                </span>
            ))}
        </span>
    )
}
