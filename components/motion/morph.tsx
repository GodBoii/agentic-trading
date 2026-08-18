'use client'

import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

/**
 * Recipe 20 — trigger-to-surface morph.
 *
 * The trigger *becomes* the surface it opens: its box grows, its corner radius
 * relaxes, the resting content cross-fades and slides out, and the panel
 * slides in from the other side. Opening uses a bouncier curve than closing —
 * the two must not be collapsed into one variable.
 *
 * Chosen over a dropdown here because the trigger and the surface are the same
 * element. The Dhan control is a single pill that expands in place into the
 * client-ID field; a dropdown would imply a separate popover appearing beside
 * a button that stayed put.
 *
 * `overflow: hidden` on the container is load-bearing: it clips the incoming
 * panel while the box is still growing, so the content does not spill outside
 * the rounded frame mid-transition.
 *
 * Both states' dimensions are supplied by the caller and applied inline. They
 * cannot be derived from content, because animating `width`/`height` requires
 * concrete values at both ends — `auto` has nothing to interpolate toward.
 */
export function Morph({
    open,
    resting,
    expanded,
    closedSize,
    openSize,
    className,
    label,
}: {
    open: boolean
    /** Shown when closed — the trigger's own content. */
    resting: ReactNode
    /** Shown when open — the surface the trigger became. */
    expanded: ReactNode
    closedSize: { width: number | string; height: number | string }
    openSize: { width: number | string; height: number | string }
    className?: string
    label?: string
}) {
    const size = open ? openSize : closedSize

    return (
        <div
            className={cn('t-morph', className)}
            data-open={open}
            aria-label={label}
            style={{ width: size.width, height: size.height }}
        >
            {/* The panel sits underneath and is revealed as the box grows. */}
            <div className="t-morph-menu absolute inset-0">{expanded}</div>
            {/* The resting content overlays it, pinned so it does not get
                shoved around while the container resizes. */}
            <div className="t-morph-plus absolute inset-0">{resting}</div>
        </div>
    )
}
