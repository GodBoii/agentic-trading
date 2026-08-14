import { cn } from '@/lib/cn'

const TONE_FILL = {
    accent: 'bg-accent',
    positive: 'bg-positive',
    negative: 'bg-negative',
    warning: 'bg-warning',
    neutral: 'bg-line-strong',
} as const

export type MeterTone = keyof typeof TONE_FILL

/** Proportion of a known total. Exposed to assistive tech as a progressbar. */
export function Meter({
    value,
    tone = 'accent',
    label,
    className,
}: {
    /** Percentage, 0–100. Clamped. */
    value: number
    tone?: MeterTone
    label?: string
    className?: string
}) {
    const clamped = Math.min(100, Math.max(0, Number.isFinite(value) ? value : 0))
    return (
        <div
            className={cn('meter', className)}
            role="progressbar"
            aria-valuenow={Math.round(clamped)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={label}
        >
            <span className={cn('meter-fill', TONE_FILL[tone])} style={{ width: `${clamped}%` }} />
        </div>
    )
}
