'use client'

import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { cn } from '@/lib/cn'
import { forceReflow, motionMs, prefersReducedMotion } from './tokens'

/**
 * Recipe 04 — text states swap.
 *
 * Replaces a label in place: "Refresh" → "Refreshing", "Save" → "Saved",
 * "Sign out" → "Signing out". The old text exits upward with blur, the new
 * text enters from below. Symmetric at 150ms in both directions — this reads
 * as one reversible motion, not an open/close pair, so the durations must
 * not be split.
 *
 * Why one node that swaps its own text, rather than cross-fading two stacked
 * copies: the label sits inside a button whose width comes from its content.
 * Two copies would need a fixed width or would fight over the layout; one
 * node keeps the button's intrinsic sizing intact.
 */

/** `useLayoutEffect` on the client, a no-op during SSR (where it warns). */
const useIsomorphicLayoutEffect = typeof window === 'undefined' ? useEffect : useLayoutEffect

export function TextSwap({
    children,
    className,
}: {
    /** The current label. Changing it plays the swap. */
    children: string
    className?: string
}) {
    const ref = useRef<HTMLSpanElement | null>(null)
    /** What the DOM currently shows — lags `children` by one exit phase. */
    const [rendered, setRendered] = useState(children)
    const [exiting, setExiting] = useState(false)
    /** Set when `rendered` has just changed and still needs its entrance. */
    const needsEntrance = useRef(false)
    const timer = useRef<number | null>(null)

    useEffect(() => {
        if (children === rendered) return

        if (prefersReducedMotion()) {
            setRendered(children)
            return
        }

        // Phase 1 — the outgoing text lifts, blurs and fades.
        setExiting(true)
        if (timer.current) window.clearTimeout(timer.current)
        timer.current = window.setTimeout(() => {
            // Phase 2 — content swaps and the exit class drops in the same
            // commit, so the node is never painted at rest with the new text.
            needsEntrance.current = true
            setExiting(false)
            setRendered(children)
        }, motionMs('--text-swap-dur', 150))
        // `rendered` is intentionally read but not depended on: adding it
        // would restart the exit timer mid-flight when phase 2 lands.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [children])

    useEffect(
        () => () => {
            if (timer.current) window.clearTimeout(timer.current)
        },
        [],
    )

    // Phase 3 — park the new text below with transitions suspended, force a
    // reflow, then release it so it animates up to rest. This must run before
    // paint, or the new label flashes at its resting position first.
    useIsomorphicLayoutEffect(() => {
        const node = ref.current
        if (!node || !needsEntrance.current) return
        needsEntrance.current = false
        if (prefersReducedMotion()) return
        node.classList.add('is-enter-start')
        forceReflow(node)
        node.classList.remove('is-enter-start')
    }, [rendered])

    return (
        <span ref={ref} className={cn('t-text-swap', exiting && 'is-exit', className)}>
            {rendered}
        </span>
    )
}
