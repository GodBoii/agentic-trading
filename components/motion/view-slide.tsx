'use client'

import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { cn } from '@/lib/cn'
import { motionNum, prefersReducedMotion } from './tokens'

const useIsomorphicLayoutEffect = typeof window === 'undefined' ? useEffect : useLayoutEffect

/**
 * Recipe 08 — page side-by-side, for a switcher with more than two views.
 *
 * `PageSwitch` stages both surfaces so each can exit as the other enters, which
 * is right for a list ⇄ detail pair. A tab panel with three or more options
 * cannot work that way: it would need every panel mounted at once, and on this
 * screen each panel is a full data table.
 *
 * So only the incoming view renders, but it still travels from the side it came
 * from. That preserves the part of the recipe that carries meaning — the
 * direction tells the reader which way they moved through the options — using
 * the same 8px travel, 3px blur and 250ms clock.
 *
 * Direction is derived from the index, so the caller only supplies an ordered
 * list and the current position.
 */
export function ViewSlide({
    /** Position of the active view in its ordered set. */
    index,
    children,
    className,
}: {
    index: number
    children: ReactNode
    className?: string
}) {
    const [entering, setEntering] = useState(false)
    const previous = useRef(index)
    /** First paint has nothing to travel from. */
    const painted = useRef(false)
    const [fromX, setFromX] = useState(0)

    useIsomorphicLayoutEffect(() => {
        if (!painted.current) {
            painted.current = true
            previous.current = index
            return
        }
        if (index === previous.current) return

        const forward = index > previous.current
        previous.current = index
        if (prefersReducedMotion()) return

        // Entering from the right when moving forward, from the left when
        // moving back — the same convention as the two-page slide.
        const distance = motionNum('--page-slide-distance', 8)
        setFromX(forward ? distance : -distance)
        setEntering(true)
    }, [index])

    // Release on the next frame so the offset state is painted first; setting
    // and clearing in one commit gives the transition nothing to interpolate.
    useEffect(() => {
        if (!entering) return
        const frame = requestAnimationFrame(() => setEntering(false))
        return () => cancelAnimationFrame(frame)
    }, [entering])

    return (
        <div
            className={cn('t-view', className)}
            data-enter={entering || undefined}
            style={{ '--view-from-x': `${fromX}px` } as CSSProperties}
        >
            {children}
        </div>
    )
}
