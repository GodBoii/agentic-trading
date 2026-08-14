import { cn } from '@/lib/cn'

/** Indeterminate activity. Animation is suppressed under reduced-motion. */
export function Spinner({ size = 12, className }: { size?: number; className?: string }) {
    return (
        <span
            aria-hidden
            className={cn('archive-spinner inline-block flex-shrink-0', className)}
            style={{ width: size, height: size }}
        />
    )
}
