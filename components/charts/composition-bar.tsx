import { cn } from '@/lib/cn'

/**
 * CompositionBar — a single 100% stacked bar plus a legend that carries the
 * numbers.
 *
 * Built from percentage-width elements rather than SVG: no measurement or
 * ResizeObserver, and no marker distortion when the container is resized.
 *
 * The bar itself is `aria-hidden`; the legend is the accessible representation,
 * which is why every segment's value and share appear there as text.
 */

export type SegmentTone = 'accent' | 'positive' | 'negative' | 'warning' | 'neutral'

export interface CompositionSegment {
    key: string
    label: string
    value: number
    /** Explicit semantic colour. Omit to use the ranked accent ramp. */
    tone?: SegmentTone
    /** Secondary text in the legend, e.g. quantity or venue. */
    meta?: string
}

const TONE_COLOR: Record<SegmentTone, string> = {
    accent: 'var(--accent)',
    positive: 'var(--dash-positive)',
    negative: 'var(--dash-negative)',
    warning: 'var(--dash-warning)',
    neutral: 'rgba(255,255,255,0.22)',
}

/**
 * Ranked segments get one hue at descending opacity rather than categorical
 * colours — the ordering is the information, and eight arbitrary hues would
 * imply distinctions that do not exist.
 */
function rampColor(index: number, total: number) {
    if (total <= 1) return 'rgb(var(--accent-rgb) / 0.85)'
    const opacity = 0.85 - (index / (total - 1)) * 0.6
    return `rgb(var(--accent-rgb) / ${opacity.toFixed(3)})`
}

function segmentColor(segment: CompositionSegment, index: number, total: number) {
    return segment.tone ? TONE_COLOR[segment.tone] : rampColor(index, total)
}

/**
 * Collapse a long tail so the bar stays legible. Returns the top `limit`
 * segments by value plus an aggregated remainder.
 */
export function topSegments(segments: CompositionSegment[], limit = 6): CompositionSegment[] {
    if (segments.length <= limit) return [...segments].sort((a, b) => b.value - a.value)
    const sorted = [...segments].sort((a, b) => b.value - a.value)
    const head = sorted.slice(0, limit)
    const tail = sorted.slice(limit)
    const remainder = tail.reduce((sum, item) => sum + item.value, 0)
    return [
        ...head,
        {
            key: '__other__',
            label: `Other`,
            value: remainder,
            tone: 'neutral',
            meta: `${tail.length} more`,
        },
    ]
}

export function CompositionBar({
    segments,
    formatValue,
    height = 8,
    legend = true,
    legendColumns = 2,
    className,
    emptyLabel = 'Nothing to allocate yet',
}: {
    segments: CompositionSegment[]
    formatValue: (value: number) => string
    height?: number
    legend?: boolean
    legendColumns?: 1 | 2
    className?: string
    emptyLabel?: string
}) {
    const positive = segments.filter((segment) => segment.value > 0)
    const total = positive.reduce((sum, segment) => sum + segment.value, 0)

    if (!total) {
        return <p className={cn('text-[11px] text-ink-tertiary', className)}>{emptyLabel}</p>
    }

    return (
        <div className={className}>
            <div
                aria-hidden
                className="flex w-full gap-px overflow-hidden rounded-full bg-line"
                style={{ height }}
            >
                {positive.map((segment, index) => (
                    <span
                        key={segment.key}
                        className="chart-grow"
                        title={`${segment.label} · ${formatValue(segment.value)}`}
                        style={{
                            width: `${(segment.value / total) * 100}%`,
                            background: segmentColor(segment, index, positive.length),
                            /* Keeps hairline slices from disappearing entirely. */
                            minWidth: 2,
                        }}
                    />
                ))}
            </div>

            {legend && (
                <ul
                    className={cn(
                        'mt-4 grid gap-x-6 gap-y-2.5',
                        legendColumns === 2 ? 'sm:grid-cols-2' : 'grid-cols-1',
                    )}
                >
                    {positive.map((segment, index) => (
                        <li key={segment.key} className="flex items-center gap-2.5">
                            <span
                                aria-hidden
                                className="h-2 w-2 flex-shrink-0 rounded-sm"
                                style={{ background: segmentColor(segment, index, positive.length) }}
                            />
                            <span className="min-w-0 flex-1 truncate text-[11.5px] text-ink-secondary">
                                {segment.label}
                                {segment.meta && <span className="ml-1.5 text-ink-tertiary">{segment.meta}</span>}
                            </span>
                            <span className="nums flex-shrink-0 font-mono text-[11px] text-ink-primary">
                                {formatValue(segment.value)}
                            </span>
                            <span className="nums w-11 flex-shrink-0 text-right font-mono text-[10px] text-ink-tertiary">
                                {((segment.value / total) * 100).toFixed(1)}%
                            </span>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    )
}
