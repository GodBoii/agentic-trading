import { cn } from '@/lib/cn'
import { directionOf } from '@/lib/format'

/**
 * DivergingBars — signed magnitudes around a shared zero axis.
 *
 * The correct chart for "which positions made money and which lost it": a
 * plain bar chart forces the reader to decode sign from colour alone, whereas
 * direction from the axis is pre-attentive. Bars are scaled against the largest
 * absolute value so the worst loss and the best gain are directly comparable.
 */

export interface DivergingItem {
    key: string
    label: string
    value: number
    /** Optional context shown under the label, e.g. "12 qty · INTRADAY". */
    meta?: string
}

export function DivergingBars({
    items,
    formatValue,
    className,
    emptyLabel = 'No data to compare',
}: {
    items: DivergingItem[]
    formatValue: (value: number) => string
    className?: string
    emptyLabel?: string
}) {
    if (!items.length) {
        return <p className={cn('text-[11px] text-ink-tertiary', className)}>{emptyLabel}</p>
    }

    const maxAbs = items.reduce((max, item) => Math.max(max, Math.abs(item.value)), 0)
    // Ranked worst-to-best reads as a distribution rather than an arbitrary list.
    const ordered = [...items].sort((a, b) => b.value - a.value)

    return (
        <ul className={cn('space-y-2', className)}>
            {ordered.map((item) => {
                const direction = directionOf(item.value)
                const share = maxAbs > 0 ? (Math.abs(item.value) / maxAbs) * 100 : 0
                const positive = item.value > 0
                return (
                    <li key={item.key} className="grid grid-cols-[minmax(0,7.5rem)_1fr_minmax(0,5.5rem)] items-center gap-3">
                        <div className="min-w-0">
                            <p className="truncate text-[11.5px] font-medium text-ink-primary">{item.label}</p>
                            {item.meta && <p className="truncate font-mono text-[9px] text-ink-tertiary">{item.meta}</p>}
                        </div>

                        {/* Two mirrored tracks meeting at the zero axis. */}
                        <div aria-hidden className="relative flex h-4 items-center">
                            <div className="flex h-full w-1/2 items-center justify-end">
                                {!positive && item.value !== 0 && (
                                    <span
                                        className="h-[7px] rounded-l-sm bg-negative/80"
                                        style={{ width: `${share}%` }}
                                    />
                                )}
                            </div>
                            <span className="h-4 w-px flex-shrink-0 bg-line-strong" />
                            <div className="flex h-full w-1/2 items-center">
                                {positive && (
                                    <span
                                        className="h-[7px] rounded-r-sm bg-positive/80"
                                        style={{ width: `${share}%` }}
                                    />
                                )}
                            </div>
                        </div>

                        <span
                            className={cn(
                                'nums text-right font-mono text-[11px]',
                                direction === 'positive' && 'text-positive',
                                direction === 'negative' && 'text-negative',
                                direction === 'neutral' && 'text-ink-tertiary',
                            )}
                        >
                            {formatValue(item.value)}
                        </span>
                    </li>
                )
            })}
        </ul>
    )
}
