'use client'

import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

/**
 * Recipe 03 — notification badge.
 *
 * The badge slides in diagonally while its dot pops with an overshoot. The
 * two are separated on purpose: only the badge moves, so the trigger it sits
 * on never shifts. Animating the trigger instead would nudge whatever is
 * beside it every time a count arrives.
 *
 * The overshoot belongs to the entrance only. On dismissal the dot scales
 * away in 180ms on a plain curve — bouncing something out is the single most
 * common way an otherwise good badge starts to feel cheap.
 *
 * The parent must be `position: relative` for the badge to anchor to it.
 */
export function NotificationBadge({
    show,
    children,
    tone = 'accent',
    className,
}: {
    show: boolean
    /** The count or label. Keep it to two or three characters. */
    children: ReactNode
    tone?: 'accent' | 'positive' | 'negative' | 'warning'
    className?: string
}) {
    return (
        <span className={cn('t-badge', className)} data-open={show} aria-hidden>
            <span
                className={cn(
                    't-badge-dot nums grid min-w-[15px] place-items-center rounded-full px-1 font-mono text-[9px] font-semibold leading-[15px]',
                    tone === 'accent' && 'bg-accent text-canvas',
                    tone === 'positive' && 'bg-positive text-canvas',
                    tone === 'negative' && 'bg-negative text-canvas',
                    tone === 'warning' && 'bg-warning text-canvas',
                )}
            >
                {children}
            </span>
        </span>
    )
}
