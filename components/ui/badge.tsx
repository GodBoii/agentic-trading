import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

export type Tone = 'neutral' | 'positive' | 'negative' | 'warning' | 'accent'
export type BadgeSize = 'sm' | 'md' | 'lg'

/**
 * Styled with Tailwind rather than the `.dash-badge` CSS class so that size is
 * a real variant. Overriding a fixed-size CSS class from the call site needs
 * `!important`, which is how badge sizing ends up inconsistent per screen.
 */
const BADGE_TONE: Record<Tone, string> = {
    neutral: 'border-line bg-white/[0.03] text-ink-secondary',
    positive: 'border-positive/25 bg-positive/[0.06] text-positive',
    negative: 'border-negative/25 bg-negative/[0.06] text-negative',
    warning: 'border-warning/25 bg-warning/[0.06] text-warning',
    accent: 'border-accent/25 bg-accent/[0.06] text-accent',
}

const BADGE_SIZE: Record<BadgeSize, string> = {
    sm: 'px-1.5 py-px text-[9px]',
    md: 'px-2 py-0.5 text-[10px]',
    lg: 'px-2.5 py-1 text-[11px]',
}

const DOT_TONE: Record<Tone, string> = {
    neutral: 'dash-dot-muted',
    positive: 'dash-dot-positive',
    negative: 'dash-dot-negative',
    warning: 'dash-dot-warning',
    accent: 'dash-dot-accent',
}

/** Compact uppercase state marker. */
export function Badge({
    children,
    tone = 'neutral',
    size = 'md',
    className,
}: {
    children: ReactNode
    tone?: Tone
    size?: BadgeSize
    className?: string
}) {
    return (
        <span
            className={cn(
                'inline-flex max-w-full items-center gap-1 truncate rounded-full border font-mono font-medium uppercase tracking-[0.08em]',
                BADGE_TONE[tone],
                BADGE_SIZE[size],
                className,
            )}
        >
            {children}
        </span>
    )
}

/**
 * The lowest-weight state indicator, for places where a filled badge would be
 * too loud — table rows, list items, connection status.
 */
export function StatusDot({
    tone = 'neutral',
    pulse,
    className,
}: {
    tone?: Tone
    pulse?: boolean
    className?: string
}) {
    return <span aria-hidden className={cn('dash-dot', DOT_TONE[tone], pulse && 'dash-dot-pulse', className)} />
}

export function StatusChip({
    children,
    tone = 'neutral',
    pulse,
    className,
}: {
    children: ReactNode
    tone?: Tone
    pulse?: boolean
    className?: string
}) {
    return (
        <span className={cn('product-chip', className)}>
            <StatusDot tone={tone} pulse={pulse} />
            {children}
        </span>
    )
}
