import type { CSSProperties } from 'react'
import { cn } from '@/lib/cn'

/**
 * Shimmer placeholder.
 *
 * The sweeping highlight runs on `linear` easing: an eased sweep decelerates at
 * each end of its travel, which reads as a stutter rather than a loop.
 *
 * `delay` offsets the sweep. The animation lives on a pseudo-element, so the
 * offset is passed as a custom property rather than an inline
 * `animation-delay` — an inline style cannot reach `::after`.
 */
export function Skeleton({ className, delay = 0 }: { className?: string; delay?: number }) {
    return (
        <div
            aria-hidden
            className={cn('archive-skeleton rounded-lg bg-surface-soft', className)}
            style={delay ? ({ '--skeleton-delay': `${delay}ms` } as CSSProperties) : undefined}
        />
    )
}

/**
 * Placeholder shaped like a populated table, so the layout does not jump when
 * real rows land. Row heights match `.data-table` cell padding.
 *
 * Rows are staggered by 40ms — the same per-item offset the real content uses
 * when it arrives — so the placeholder reads as a list filling in rather than
 * one solid block pulsing as a single object. The offset is capped so the last
 * row of a long table is not a second behind its first.
 */
export function SkeletonRows({ rows = 6, columns = 5 }: { rows?: number; columns?: number }) {
    return (
        <div className="p-1" aria-hidden>
            {Array.from({ length: rows }, (_, row) => (
                <div key={row} className="flex items-center gap-4 border-b border-line px-4 py-[13px] last:border-b-0">
                    {Array.from({ length: columns }, (_, column) => (
                        <Skeleton
                            key={column}
                            delay={Math.min(row, 6) * 40}
                            className={cn('h-2.5', column === 0 ? 'w-[22%]' : 'flex-1')}
                        />
                    ))}
                </div>
            ))}
        </div>
    )
}
