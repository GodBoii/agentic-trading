'use client'

import { useRef } from 'react'
import { cn } from '@/lib/cn'

export interface TabItem<T extends string> {
    id: T
    label: string
    /** Row count shown beside the label. Renders even when zero. */
    count?: number
}

/**
 * SegmentedTabs — a real tablist.
 *
 * Implements the WAI-ARIA automatic-activation tabs pattern: roving tabindex
 * plus Arrow/Home/End handling, so the control is operable without a mouse.
 * The previous tab strips were plain buttons with no tablist semantics.
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
        <div className={cn('product-tabs', className)} role="tablist" aria-label={ariaLabel}>
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
                        data-active={active}
                        onClick={() => onChange(item.id)}
                        onKeyDown={(event) => onKeyDown(event, index)}
                        className="product-tab"
                    >
                        {item.label}
                        {item.count !== undefined && (
                            <span className={cn('nums font-mono text-[10px]', active ? 'text-ink-secondary' : 'text-ink-tertiary')}>
                                {item.count}
                            </span>
                        )}
                    </button>
                )
            })}
        </div>
    )
}
