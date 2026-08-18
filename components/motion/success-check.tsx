'use client'

import { useEffect, useRef, useState } from 'react'
import { cn } from '@/lib/cn'
import { forceReflow } from './tokens'

/**
 * Recipe 10 — success check.
 *
 * Fade, rotate upright, settle with a Y-bob, and draw the tick's stroke — all
 * in parallel over 500ms, with the path draw held back by an 80ms intent beat
 * so the mark lands *after* the badge has arrived rather than alongside it.
 *
 * Used where a state genuinely changes from "pending" to "done": the broker
 * connected, the account created, the amount saved. The recipe covers the
 * appear only; success states are usually persistent, and a soft fade-out is
 * rarely worth the extra machinery.
 *
 * `stroke-dasharray` must equal the path's own length or the stroke either
 * pre-reveals or over-draws. Rather than hardcoding a number that silently
 * breaks if the path is ever edited, the length is measured on mount with
 * `getTotalLength()` and written to `--check-len`.
 */
export function SuccessCheck({
    /** Flip to `true` to play. Re-arming replays from the start. */
    play = true,
    size = 20,
    className,
}: {
    play?: boolean
    size?: number
    className?: string
}) {
    const wrapper = useRef<HTMLSpanElement | null>(null)
    const path = useRef<SVGPathElement | null>(null)
    const [state, setState] = useState<'out' | 'in'>('out')

    // Measure once, rounding up by a pixel to absorb sub-pixel float jitter.
    useEffect(() => {
        const node = path.current
        const host = wrapper.current
        if (!node || !host) return
        const length = Math.ceil(node.getTotalLength()) + 1
        host.style.setProperty('--check-len', String(length))
    }, [])

    useEffect(() => {
        if (!play) {
            setState('out')
            return
        }
        // Reset → reflow → play, so re-triggering restarts the keyframes
        // instead of leaving them parked at their end state.
        setState('out')
        forceReflow(wrapper.current)
        const frame = requestAnimationFrame(() => setState('in'))
        return () => cancelAnimationFrame(frame)
    }, [play])

    return (
        <span
            ref={wrapper}
            className={cn('t-success-check', className)}
            data-state={state}
            aria-hidden
            style={{ width: size, height: size }}
        >
            <svg viewBox="0 0 24 24" width={size} height={size} fill="none">
                <path
                    ref={path}
                    d="M5 12.5L9.5 17L19 7"
                    stroke="currentColor"
                    strokeWidth={2.25}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                />
            </svg>
        </span>
    )
}

/**
 * The check inside a toned badge, for a full-width confirmation panel where
 * the mark is the focal point rather than an inline annotation.
 */
export function SuccessBadge({
    play = true,
    size = 64,
    className,
}: {
    play?: boolean
    size?: number
    className?: string
}) {
    return (
        <span
            className={cn(
                'grid place-items-center rounded-full border border-positive/30 bg-positive/[0.08] text-positive',
                className,
            )}
            style={{ width: size, height: size }}
        >
            <SuccessCheck play={play} size={Math.round(size * 0.44)} />
        </span>
    )
}
