'use client'

import { useId, type ReactNode } from 'react'
import { cn } from '@/lib/cn'

/**
 * Recipe 17 — tooltip open / close.
 *
 * Fades and scales in after an 80ms intent delay, and leaves in 50ms with no
 * delay at all. The asymmetry is the point: the delay filters out a cursor
 * merely passing over the trigger, while dismissal has to feel instant.
 *
 * Pure CSS, and the *wrapper* is the hover target rather than the trigger, so
 * the pointer can drift onto the tooltip without the surface flickering out
 * from under it.
 *
 * This replaces the bare `title` attributes that were carrying real
 * explanations — stream health, truncated identifiers. A native `title` has
 * an uncontrollable ~1s delay, cannot be styled, is invisible to touch, and
 * never appears for keyboard users. `aria-describedby` wires the tooltip to
 * its trigger so assistive tech reads it either way.
 */
export function Tooltip({
    label,
    children,
    align = 'center',
    className,
}: {
    /** The explanation. Keep it to a sentence — this is a hint, not a panel. */
    label: ReactNode
    /** The trigger. Must be focusable for the hint to reach keyboard users. */
    children: ReactNode
    align?: 'center' | 'end'
    className?: string
}) {
    const id = useId()

    return (
        <span className={cn('t-tt-wrap', className)}>
            <span className="t-tt-trigger inline-flex" aria-describedby={id}>
                {children}
            </span>
            <span className="t-tt" id={id} role="tooltip" data-align={align === 'end' ? 'end' : undefined}>
                {label}
            </span>
        </span>
    )
}
