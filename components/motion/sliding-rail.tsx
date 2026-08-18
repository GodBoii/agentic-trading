'use client'

import { useCallback, useEffect, useLayoutEffect, useRef, type ReactNode } from 'react'
import { cn } from '@/lib/cn'

const useIsomorphicLayoutEffect = typeof window === 'undefined' ? useEffect : useLayoutEffect

/**
 * Recipe 16 — tabs sliding, applied to route navigation.
 *
 * The same measured-pill mechanics `SegmentedTabs` uses, but for a set of
 * links where the active item is determined by the current route rather than
 * by local state. The distinction matters for semantics: these are `<a>`
 * elements marked `aria-current="page"`, not tabs, so they must not claim
 * `role="tab"` or live inside a `tablist`.
 *
 * The pill travels between sections on navigation, which does real work in a
 * three-section app: it shows where you came from, so a route change is
 * attributable rather than just a new screen appearing.
 *
 * Geometry has to be measured and written inline — CSS cannot know the width
 * of a link whose label is an arbitrary string.
 */
export function SlidingRail({
    children,
    /** Selector matching the active item inside this rail. */
    activeKey,
    ariaLabel,
    className,
}: {
    children: ReactNode
    /**
     * Changes whenever the active item changes. Used only as a dependency, so
     * the pill re-measures after the new item has been marked current.
     */
    activeKey: string
    ariaLabel: string
    className?: string
}) {
    const rail = useRef<HTMLElement | null>(null)
    const pill = useRef<HTMLSpanElement | null>(null)
    const painted = useRef(false)

    const movePill = useCallback((animate: boolean) => {
        const host = rail.current
        const node = pill.current
        if (!host || !node) return

        const target = host.querySelector<HTMLElement>('[aria-current="page"]')
        if (!target) {
            // Nothing current (an unmatched route): retract rather than
            // leaving the pill stranded under the wrong item.
            node.style.width = '0px'
            return
        }

        const write = () => {
            node.style.transform = `translateX(${target.offsetLeft}px)`
            node.style.width = `${target.offsetWidth}px`
        }

        if (animate) {
            write()
            return
        }

        // Snap on first paint and on resize: suspend, write, reflow, restore.
        // Without this the pill animates in from zero width every time.
        const previous = node.style.transition
        node.style.transition = 'none'
        write()
        void node.offsetWidth
        node.style.transition = previous
    }, [])

    useIsomorphicLayoutEffect(() => {
        movePill(painted.current)
        painted.current = true
    }, [movePill, activeKey])

    useEffect(() => {
        const onResize = () => movePill(false)
        window.addEventListener('resize', onResize)
        return () => window.removeEventListener('resize', onResize)
    }, [movePill])

    return (
        <nav ref={rail} className={cn('t-tabs', className)} aria-label={ariaLabel}>
            <span ref={pill} className="t-tabs-pill" aria-hidden />
            {children}
        </nav>
    )
}
