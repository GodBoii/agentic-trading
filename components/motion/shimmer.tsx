'use client'

import { cn } from '@/lib/cn'

/**
 * Recipe 15 — shimmer text.
 *
 * A highlight band sweeps across muted copy on a 2s linear loop. Pure CSS: no
 * JS, no class toggling, nothing to tear down.
 *
 * The right treatment for in-progress *prose* — "Analysing", "Streaming
 * agent events", "Connecting" — where a spinner beside a word says only that
 * something is happening, while a live label says what. It also avoids the
 * spinner's worst habit: a fixed-size glyph next to text of a different size,
 * never quite optically aligned.
 *
 * The string is duplicated into `data-text` because the sweep is painted onto
 * a `::before` layer and clipped to the glyphs with `background-clip: text`.
 * Taking the visible copy from `children` and mirroring it into the attribute
 * in one component keeps the two from drifting apart.
 */
export function Shimmer({
    children,
    className,
}: {
    /** Plain text only — the sweep clips to glyphs, not to nested elements. */
    children: string
    className?: string
}) {
    return (
        <span className={cn('t-shimmer', className)} data-text={children}>
            {children}
        </span>
    )
}
