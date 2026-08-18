'use client'

import { useCallback, useEffect, useLayoutEffect, useRef } from 'react'
import { cn } from '@/lib/cn'

const useIsomorphicLayoutEffect = typeof window === 'undefined' ? useEffect : useLayoutEffect

export interface TabItem<T extends string> {
    id: T
    label: string
    /** Row count shown beside the label. Renders even when zero. */
    count?: number
}

/**
 * SegmentedTabs — a real tablist with a sliding active pill.
 *
 * Behaviour: implements the WAI-ARIA automatic-activation tabs pattern —
 * roving tabindex plus Arrow/Home/End handling — so the control is fully
 * operable without a mouse.
 *
 * Motion (recipe 16): the active pill travels between options over 250ms
 * instead of the background colour cutting from one tab to the next. The
 * movement is what carries the meaning: it shows *which* tab you came from,
 * so the change of view is attributable rather than just sudden. Symmetric in
 * both directions — moving left and moving right are the same motion.
 *
 * The pill's geometry is measured and written inline, because CSS cannot know
 * a tab's width when the labels are arbitrary strings and carry counts.
 */
export function SegmentedTabs<T extends string>({
    items,
    value,
    onChange,
    ariaLabel,
    panelId,
    className,
}: {
    items: TabItem<T>[]
    value: T
    onChange: (id: T) => void
    ariaLabel: string
    /** id of the element the tabs control, for `aria-controls`. */
    panelId?: string
    className?: string
}) {
    const buttons = useRef<(HTMLButtonElement | null)[]>([])
    const pill = useRef<HTMLSpanElement | null>(null)
    /** First paint must snap; every later move animates. */
    const painted = useRef(false)

    const movePill = useCallback((animate: boolean) => {
        const index = items.findIndex((item) => item.id === value)
        const target = buttons.current[index < 0 ? 0 : index]
        const node = pill.current
        if (!target || !node) return

        const write = () => {
            node.style.transform = `translateX(${target.offsetLeft}px)`
            node.style.width = `${target.offsetWidth}px`
        }

        if (animate) {
            write()
            return
        }

        // Suspend the transition, write, reflow, restore. Without this the
        // pill animates in from translateX(0)/width:0 on mount and on every
        // resize, which reads as the control assembling itself.
        const previous = node.style.transition
        node.style.transition = 'none'
        write()
        void node.offsetWidth
        node.style.transition = previous
    }, [items, value])

    useIsomorphicLayoutEffect(() => {
        movePill(painted.current)
        painted.current = true
    }, [movePill])

    // Reflow changes tab widths, so the pill has to be re-measured — and
    // snapped, not animated, since nothing was activated.
    useEffect(() => {
        const onResize = () => movePill(false)
        window.addEventListener('resize', onResize)
        return () => window.removeEventListener('resize', onResize)
    }, [movePill])

    const move = (from: number, delta: number) => {
        const next = (from + delta + items.length) % items.length
        onChange(items[next].id)
        buttons.current[next]?.focus()
    }

    const onKeyDown = (event: React.KeyboardEvent, index: number) => {
        switch (event.key) {
            case 'ArrowRight':
                event.preventDefault()
                move(index, 1)
                break
            case 'ArrowLeft':
                event.preventDefault()
                move(index, -1)
                break
            case 'Home':
                event.preventDefault()
                move(0, 0)
                break
            case 'End':
                event.preventDefault()
                move(items.length - 1, 0)
                break
        }
    }

    return (
        <div className={cn('t-tabs', className)} role="tablist" aria-label={ariaLabel}>
            <span ref={pill} className="t-tabs-pill" aria-hidden />
            {items.map((item, index) => {
                const active = item.id === value
                return (
                    <button
                        key={item.id}
                        ref={(node) => {
                            buttons.current[index] = node
                        }}
                        type="button"
                        role="tab"
                        id={`tab-${item.id}`}
                        aria-selected={active}
                        aria-controls={panelId}
                        tabIndex={active ? 0 : -1}
                        onClick={() => onChange(item.id)}
                        onKeyDown={(event) => onKeyDown(event, index)}
                        className="t-tab"
                    >
                        {item.label}
                        {item.count !== undefined && <span className="t-tab-count">{item.count}</span>}
                    </button>
                )
            })}
        </div>
    )
}
