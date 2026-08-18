'use client'

import {
    Children,
    isValidElement,
    useEffect,
    useRef,
    useState,
    type ElementType,
    type ReactNode,
} from 'react'
import { cn } from '@/lib/cn'

/**
 * Recipe 18 — texts reveal.
 *
 * Stacked copy rises into view with staggered blur. Replaces the
 * `framer-motion` `initial`/`whileInView` fade-ups that were hand-tuned
 * per component (durations of 0.7s and 0.8s, delays of 0.06s, 0.08s, 0.1s,
 * 0.15s, 0.2s, 0.25s and 0.45s across six files, all slightly different).
 * Everything now runs on the shared `--stagger-*` tokens, so the landing
 * page, the auth screens and every page header share one rhythm.
 *
 * The stagger offset is 40ms per line and the number of staggered lines is
 * capped at seven, keeping the total under ~300ms so the last line never
 * feels like it arrived late.
 */

/**
 * Fires once when the element first enters the viewport.
 *
 * `once` is deliberate: re-playing an entrance every time the reader
 * scrolls back up turns a reveal into a distraction.
 */
export function useReveal<T extends HTMLElement = HTMLDivElement>({
    margin = '-10%',
    immediate = false,
}: { margin?: string; immediate?: boolean } = {}) {
    const ref = useRef<T | null>(null)
    const [shown, setShown] = useState(false)

    useEffect(() => {
        // Above-the-fold copy should not wait for an intersection callback.
        if (immediate) {
            // One frame, so the browser paints the pre-reveal state first and
            // the transition has two values to interpolate between.
            const frame = requestAnimationFrame(() => setShown(true))
            return () => cancelAnimationFrame(frame)
        }

        const node = ref.current
        if (!node) return

        // No IntersectionObserver (or SSR-restored markup): show immediately
        // rather than leaving the copy permanently invisible.
        if (typeof IntersectionObserver === 'undefined') {
            setShown(true)
            return
        }

        const observer = new IntersectionObserver(
            (entries) => {
                if (entries.some((entry) => entry.isIntersecting)) {
                    setShown(true)
                    observer.disconnect()
                }
            },
            { rootMargin: margin, threshold: 0.01 },
        )
        observer.observe(node)
        return () => observer.disconnect()
    }, [margin, immediate])

    return { ref, shown }
}

const MAX_STAGGER_LINES = 7

/**
 * Wraps each child in a staggered line. Children are used as-is, so the
 * caller keeps control of the element type and typography.
 */
export function Reveal({
    children,
    className,
    as: Tag = 'div',
    immediate = false,
    margin,
    /** Offsets the stagger, for a block that continues an earlier one. */
    startAt = 0,
}: {
    children: ReactNode
    className?: string
    as?: ElementType
    /** Play on mount instead of on scroll. Use above the fold. */
    immediate?: boolean
    margin?: string
    startAt?: number
}) {
    const { ref, shown } = useReveal<HTMLElement>({ margin, immediate })
    const items = Children.toArray(children).filter(isValidElement)

    return (
        <Tag ref={ref} className={cn('t-stagger', shown && 'is-shown', className)}>
            {items.map((child, index) => {
                const line = Math.min(startAt + index + 1, MAX_STAGGER_LINES)
                return (
                    <div key={child.key ?? index} className={`t-stagger-line t-stagger-line--${line}`}>
                        {child}
                    </div>
                )
            })}
        </Tag>
    )
}

/**
 * A single revealed block, for cases where the extra wrapper `div` per line
 * would break a layout (grid children, list items, table rows).
 */
export function RevealBlock({
    children,
    className,
    as: Tag = 'div',
    line = 1,
    immediate = false,
    margin,
}: {
    children: ReactNode
    className?: string
    as?: ElementType
    /** 1-based position in the stagger. Clamped to the token ramp. */
    line?: number
    immediate?: boolean
    margin?: string
}) {
    const { ref, shown } = useReveal<HTMLElement>({ margin, immediate })
    const clamped = Math.min(Math.max(line, 1), MAX_STAGGER_LINES)

    return (
        <Tag
            ref={ref}
            className={cn('t-stagger', shown && 'is-shown', className)}
        >
            <div className={`t-stagger-line t-stagger-line--${clamped}`}>{children}</div>
        </Tag>
    )
}

/**
 * Reveals a list of siblings that must stay direct children of their parent
 * (grid cells, `<li>`s). The parent gets the trigger; each child carries its
 * own stagger position.
 *
 * Returns the props to spread, rather than rendering a wrapper, precisely
 * because inserting one would break `display: grid` and `.cell-grid`.
 */
export function useRevealList<T extends HTMLElement = HTMLDivElement>({
    margin,
    immediate,
}: { margin?: string; immediate?: boolean } = {}) {
    const { ref, shown } = useReveal<T>({ margin, immediate })

    return {
        containerProps: {
            ref,
            className: cn('t-stagger', shown && 'is-shown'),
        },
        /** Stagger class for the item at `index` (0-based). */
        lineClass: (index: number) =>
            `t-stagger-line t-stagger-line--${Math.min(index + 1, MAX_STAGGER_LINES)}`,
        shown,
    }
}
