import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'
import type { Direction } from '@/lib/format'
import { NumberFlow } from '@/components/motion/number-flow'
import { Meter } from './meter'

const DIRECTION_TEXT: Record<Direction, string> = {
    positive: 'text-positive',
    negative: 'text-negative',
    neutral: 'text-ink-primary',
}

/**
 * StatTile — one figure with its label.
 *
 * `direction` colours the value by P&L sign and is the only place tone is
 * decided, so a positive number can never accidentally render red.
 * Designed to sit inside a `CellGrid`, which supplies the frame and dividers.
 *
 * Motion. When `value` is a string, it is rendered through the number pop-in
 * recipe (recipe 02): on every change the characters re-enter from below with
 * a 2px blur, the last two staggered. This is the answer to a real problem on
 * this screen — five broker figures refresh at once, and without it a number
 * silently becoming a different number is completely invisible. It marks the
 * change without demanding attention, which is why it is the pop-in and not
 * the spinning counter.
 *
 * Non-string values (a composed node) render as given; there is no single
 * string to split into characters.
 */
export function StatTile({
    label,
    value,
    note,
    direction = 'neutral',
    emphasis = 'default',
    trailing,
    meter,
    className,
}: {
    label: string
    value: ReactNode
    note?: ReactNode
    direction?: Direction
    emphasis?: 'default' | 'primary'
    /** Small right-aligned annotation on the label row, e.g. a percentage. */
    trailing?: ReactNode
    meter?: { value: number; tone?: 'accent' | 'positive' | 'negative' | 'warning' }
    className?: string
}) {
    return (
        <div className={cn('p-4 sm:p-5', className)}>
            <div className="flex items-start justify-between gap-3">
                <p className="dash-label">{label}</p>
                {trailing && (
                    <span className="nums flex-shrink-0 font-mono text-[10px] text-ink-secondary">{trailing}</span>
                )}
            </div>
            <p
                className={cn(
                    'dash-metric nums mt-3 truncate',
                    emphasis === 'primary' ? 'text-[22px]' : 'text-[18px]',
                    DIRECTION_TEXT[direction],
                )}
            >
                {typeof value === 'string' ? <NumberFlow value={value} /> : value}
            </p>
            {meter && <Meter className="mt-3" value={meter.value} tone={meter.tone} />}
            {note && <p className="mt-1.5 truncate text-[10px] text-ink-tertiary">{note}</p>}
        </div>
    )
}
