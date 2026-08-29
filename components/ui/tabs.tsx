'use client'

import { useCallback, useEffect, useLayoutEffect, useRef, type ReactNode } from 'react'
import { cn } from '@/lib/cn'

const useIsomorphicLayoutEffect = typeof window === 'undefined' ? useEffect : useLayoutEffect

export interface TabItem<T extends string> {
    id: T
    label: string
    /** Row count shown beside the label. Renders even when zero. */
    count?: number
    /**
     * Leading glyph. Decorative: the label is always present, so the icon adds
     * scanning speed rather than carrying meaning on its own.
     */
    icon?: ReactNode
    /**
     * Hide the label below `sm`, keeping the icon. Only safe on options whose
     * icon is unambiguous, so it is opt-in per item rather than a mode of the
     * whole rail — an icon-only "Trade sizing" tab would be a guess.
     */
    compact?: boolean
}

/**
 * Recipe 16 — the measured pill, shared by every control in this file.
 *
 * Geometry has to be measured and written inline: CSS cannot know the width of
 * an option whose label is an arbitrary string. `getActive` is called rather
 * than the element being passed in so the caller can look the target up
 * however suits it, and must be stable — it is a dependency of the write.
 */
function usePillRail(activeKey: string, getActive: () => HTMLElement | null) {
    const pill = useRef<HTMLSpanElement | null>(null)
    /** First paint must snap; every later move animates. */
    const painted = useRef(false)

    const movePill = useCallback(
        (animate: boolean) => {
            const target = getActive()
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
        },
        [getActive],
    )

    useIsomorphicLayoutEffect(() => {
        movePill(painted.current)
        painted.current = true
    }, [movePill, activeKey])

    // Reflow changes option widths, so the pill has to be re-measured — and
    // snapped, not animated, since nothing was activated.
    useEffect(() => {
        const onResize = () => movePill(false)
        window.addEventListener('resize', onResize)
        return () => window.removeEventListener('resize', onResize)
    }, [movePill])

    return pill
}

/** Arrow/Home/End over a roving-tabindex option row. */
function railKeyDown<T extends string>(
    event: React.KeyboardEvent,
    index: number,
    items: TabItem<T>[],
    onChange: (id: T) => void,
    buttons: React.MutableRefObject<(HTMLButtonElement | null)[]>,
    /** Radio groups answer to Up/Down as well; a horizontal tablist does not. */
    verticalKeys = false,
) {
    const move = (from: number, delta: number) => {
        const next = (from + delta + items.length) % items.length
        onChange(items[next].id)
        buttons.current[next]?.focus()
    }

    switch (event.key) {
        case 'ArrowDown':
            if (!verticalKeys) return
            event.preventDefault()
            move(index, 1)
            break
        case 'ArrowUp':
            if (!verticalKeys) return
            event.preventDefault()
            move(index, -1)
            break
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
    const getActive = useCallback(() => {
        const index = items.findIndex((item) => item.id === value)
        return buttons.current[index < 0 ? 0 : index]
    }, [items, value])
    const pill = usePillRail(value, getActive)

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
                        onKeyDown={(event) => railKeyDown(event, index, items, onChange, buttons)}
                        className="t-tab"
                    >
                        <TabFace item={item} />
                    </button>
                )
            })}
        </div>
    )
}

/**
 * The inside of an option, shared by both controls so the pill measures the
 * same content in either.
 *
 * A `compact` item keeps its label in the accessibility tree and hides it
 * visually below `sm`; `sr-only` rather than `hidden`, or the option would
 * announce as an unlabelled button on a phone.
 */
function TabFace<T extends string>({ item }: { item: TabItem<T> }) {
    return (
        <>
            {item.icon && (
                <span aria-hidden className="flex-shrink-0">
                    {item.icon}
                </span>
            )}
            <span className={item.compact ? 'sr-only sm:not-sr-only' : undefined}>{item.label}</span>
            {item.count !== undefined && <span className="t-tab-count">{item.count}</span>}
        </>
    )
}

/**
 * SegmentedChoice — the same sliding pill (recipe 16) as a radio group.
 *
 * Use this, not `SegmentedTabs`, when the selection is a *setting the user
 * commits* rather than a view they are browsing. A tablist tells assistive tech
 * "these reveal panels of the current screen"; a radio group tells it "pick one
 * of these values", which is what a form control that gets saved actually is.
 * The visual treatment is identical because the affordance is identical.
 *
 * Selection follows focus, as it does in the standard radio-group pattern, so
 * the pill's travel is the whole feedback for an arrow-key change.
 */
export function SegmentedChoice<T extends string>({
    items,
    value,
    onChange,
    ariaLabel,
    ariaLabelledBy,
    disabled,
    className,
}: {
    items: TabItem<T>[]
    value: T
    onChange: (id: T) => void
    ariaLabel?: string
    /** id of a visible label, preferred over `ariaLabel` when one exists. */
    ariaLabelledBy?: string
    disabled?: boolean
    className?: string
}) {
    const buttons = useRef<(HTMLButtonElement | null)[]>([])
    const getActive = useCallback(() => {
        const index = items.findIndex((item) => item.id === value)
        return buttons.current[index < 0 ? 0 : index]
    }, [items, value])
    const pill = usePillRail(value, getActive)

    return (
        <div
            className={cn('t-tabs', className)}
            role="radiogroup"
            aria-label={ariaLabel}
            aria-labelledby={ariaLabelledBy}
        >
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
                        role="radio"
                        aria-checked={active}
                        tabIndex={active ? 0 : -1}
                        disabled={disabled}
                        onClick={() => onChange(item.id)}
                        onKeyDown={(event) => railKeyDown(event, index, items, onChange, buttons, true)}
                        className="t-tab"
                    >
                        <TabFace item={item} />
                    </button>
                )
            })}
        </div>
    )
}
