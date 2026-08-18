'use client'

import { useEffect, useRef, useState, type ReactNode } from 'react'
import { cn } from '@/lib/cn'
import { prefersReducedMotion } from './tokens'

/**
 * Recipe 14 — skeleton loader and reveal.
 *
 * The placeholder pulses once, then both layers cross-fade with a matching
 * cross-blur over 400ms. Sharing one duration and easing across the fade-out
 * and the fade-in is what makes the swap read as a single motion rather than
 * two unrelated fades stepping on each other.
 *
 * Before this, every loading state in the app was a hard cut: the skeleton was
 * returned from an early `return` and the real content replaced it in one
 * frame. That is the single most visible roughness on a data screen, because
 * it happens on every visit.
 *
 * `flow` picks the layout strategy, and the choice matters:
 *   - Absolute (default) stacks both layers on the same coordinates, so the
 *     swap costs no layout at all. Requires the skeleton to be the same size
 *     as the content — correct for stat tiles and fixed-height rows.
 *   - Flow keeps them in normal flow, for regions whose height is unknown
 *     until the data lands (a table with an unknown row count). The cross-fade
 *     is preserved; the container just resizes with it.
 */
export function SkeletonReveal({
    loading,
    skeleton,
    children,
    className,
    flow = false,
    label = 'Loading',
}: {
    loading: boolean
    /** Placeholder shaped like the real thing, so nothing jumps. */
    skeleton: ReactNode
    children: ReactNode
    className?: string
    flow?: boolean
    label?: string
}) {
    const [revealed, setRevealed] = useState(!loading)
    const pulsing = useRef(loading)

    useEffect(() => {
        if (loading) {
            pulsing.current = true
            setRevealed(false)
            return
        }
        if (prefersReducedMotion()) {
            setRevealed(true)
            return
        }
        // A frame's grace so the content layer is mounted at its pre-reveal
        // blur before the transition starts.
        const frame = requestAnimationFrame(() => setRevealed(true))
        return () => cancelAnimationFrame(frame)
    }, [loading])

    return (
        <div
            className={cn('t-skel', flow && 't-skel-flow', revealed && 'is-revealed', className)}
            aria-busy={loading || undefined}
            aria-label={loading ? label : undefined}
        >
            <div className={cn('t-skel-skeleton', pulsing.current && 'is-pulsing')} aria-hidden>
                {skeleton}
            </div>
            <div className="t-skel-content">{children}</div>
        </div>
    )
}
