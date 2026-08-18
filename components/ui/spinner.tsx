import { cn } from '@/lib/cn'

/**
 * Indeterminate activity, as a last resort.
 *
 * A spinner says only "something is happening". Where the app can say *what*,
 * it should:
 *   - `SkeletonReveal` for content that is loading into a known shape
 *   - `Shimmer` for an in-progress label
 *   - `ThinkingOrb` for a semantic agent state
 *   - `Button swapLabel` for an action reporting its own progress
 *
 * This remains for the genuinely unknowable case — a row being fetched with no
 * shape to preview — and for pairing with `IconSwap`, where it cross-fades into
 * the icon it replaces instead of the two swapping between frames.
 *
 * The rotation is linear; easing a continuous spin makes it appear to stall
 * once per revolution.
 */
export function Spinner({ size = 12, className }: { size?: number; className?: string }) {
    return (
        <span
            aria-hidden
            className={cn('archive-spinner inline-block flex-shrink-0', className)}
            style={{ width: size, height: size }}
        />
    )
}
