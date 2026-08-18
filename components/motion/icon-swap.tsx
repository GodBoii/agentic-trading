'use client'

import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

/**
 * Recipe 09 — icon swap.
 *
 * Cross-fades two icons in one slot with blur and scale: spinner ⇄ arrow,
 * chevron ⇄ close, refresh ⇄ activity. Both icons stay mounted in the same
 * grid cell, which is the point — swapping by unmounting one and mounting
 * the other collapses the slot for a frame and shifts everything beside it.
 *
 * Symmetric at 250ms: there is no "open" and "close" here, just one
 * reversible exchange.
 */
export function IconSwap({
    showB,
    a,
    b,
    className,
    label,
}: {
    /** `false` renders slot A, `true` renders slot B. */
    showB: boolean
    a: ReactNode
    b: ReactNode
    className?: string
    /**
     * Announced when the state changes. Both icons are always in the DOM, so
     * without this a screen reader would read whichever is visually hidden.
     */
    label?: string
}) {
    return (
        <span
            className={cn('t-icon-swap', className)}
            data-state={showB ? 'b' : 'a'}
            role={label ? 'img' : undefined}
            aria-label={label}
            aria-hidden={label ? undefined : true}
        >
            <span className="t-icon" data-icon="a">
                {a}
            </span>
            <span className="t-icon" data-icon="b">
                {b}
            </span>
        </span>
    )
}
