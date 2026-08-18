'use client'

import { useEffect, useRef, useState, type ReactNode } from 'react'
import { cn } from '@/lib/cn'
import { motionMs, prefersReducedMotion } from './tokens'

/**
 * Recipe 08 — page side-by-side.
 *
 * Two views that live beside each other — list ⇄ detail, roster ⇄ workspace.
 * The list exits left, the detail exits right, each with an 8px travel and a
 * 3px cross-blur. Symmetric at 250ms: going forward and coming back are the
 * same motion reversed, so the durations must not be split.
 *
 * The 8px travel is doing real work. It is small enough not to feel like a
 * page load, but the *direction* tells the reader whether they went deeper or
 * came back out — which a plain cross-fade cannot say.
 *
 * Both surfaces are absolutely positioned during the transition, so the
 * container needs a height. Rather than requiring callers to hardcode one,
 * the height of the outgoing view is measured and held for the length of the
 * slide, then released back to `auto`. This is the one measurement the recipe
 * cannot avoid: `position: absolute` collapses the parent, and a hardcoded
 * height would clip a detail view of unknown length.
 */
export function PageSwitch({
    page,
    list,
    detail,
    className,
}: {
    /** `1` shows the list, `2` shows the detail. */
    page: 1 | 2
    list: ReactNode
    detail: ReactNode
    className?: string
}) {
    const container = useRef<HTMLDivElement | null>(null)
    const [sliding, setSliding] = useState(false)
    const [height, setHeight] = useState<number | null>(null)
    /** First paint must not slide — there is no previous view to leave. */
    const mounted = useRef(false)
    const timer = useRef<number | null>(null)

    useEffect(() => {
        if (!mounted.current) {
            mounted.current = true
            return
        }
        if (prefersReducedMotion()) return

        const node = container.current
        if (!node) return

        setHeight(node.offsetHeight)
        setSliding(true)

        if (timer.current) window.clearTimeout(timer.current)
        timer.current = window.setTimeout(() => {
            setSliding(false)
            // Release the pinned height so the new view can grow or shrink.
            setHeight(null)
        }, motionMs('--page-slide-dur', 250))

        return () => {
            if (timer.current) window.clearTimeout(timer.current)
        }
    }, [page])

    // Outside a transition the views are in normal flow, so the container
    // sizes itself and no measurement is involved.
    if (!sliding) {
        return (
            <div ref={container} className={className}>
                {page === 1 ? list : detail}
            </div>
        )
    }

    return (
        <div
            ref={container}
            className={cn('t-page-slide', className)}
            data-page={page}
            style={{ height: height ?? undefined }}
        >
            <div className="t-page" data-page-id="1">
                {list}
            </div>
            <div className="t-page" data-page-id="2">
                {detail}
            </div>
        </div>
    )
}
