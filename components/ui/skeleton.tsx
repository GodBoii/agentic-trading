import { cn } from '@/lib/cn'

/** Shimmer placeholder. Reuses the `.archive-skeleton` keyframes. */
export function Skeleton({ className }: { className?: string }) {
    return <div aria-hidden className={cn('archive-skeleton rounded-lg bg-white/[0.03]', className)} />
}

/**
 * Placeholder shaped like a populated table, so the layout does not jump when
 * real rows land. Row heights match `.data-table` cell padding.
 */
export function SkeletonRows({ rows = 6, columns = 5 }: { rows?: number; columns?: number }) {
    return (
        <div className="p-1" aria-hidden>
            {Array.from({ length: rows }, (_, row) => (
                <div key={row} className="flex items-center gap-4 border-b border-line px-4 py-[13px] last:border-b-0">
                    {Array.from({ length: columns }, (_, column) => (
                        <Skeleton
                            key={column}
                            className={cn('h-2.5', column === 0 ? 'w-[22%]' : 'flex-1')}
                        />
                    ))}
                </div>
            ))}
        </div>
    )
}
