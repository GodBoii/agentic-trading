import { cn } from '@/lib/cn'
import { price } from '@/lib/format'
import type { DecisionPlan } from '@/components/agent/decision'

/**
 * PriceLadder — the stop / entry / target triplet drawn to scale.
 *
 * A trade plan's meaning is in the *proportion* between its legs: a target
 * twice as far from entry as the stop is a materially different proposition
 * from one half as far. Listed as three numbers in a grid, that relationship
 * has to be computed in the reader's head; drawn on a shared axis it is
 * immediate. Works for both long and short setups.
 */
export function PriceLadder({ plan, className }: { plan: DecisionPlan; className?: string }) {
    const { entry, stop, target } = plan
    const legs = [stop, entry, target].filter((value): value is number => value !== undefined)

    // Needs at least two legs to express a proportion.
    if (entry === undefined || legs.length < 2) return null

    const min = Math.min(...legs)
    const max = Math.max(...legs)
    const range = max - min
    // A degenerate range (all legs equal) has nothing to draw.
    if (range <= 0) return null

    const pad = range * 0.12
    const domainMin = min - pad
    const span = range + pad * 2
    const positionOf = (value: number) => ((value - domainMin) / span) * 100

    const zone = (from: number, to: number) => ({
        left: `${positionOf(Math.min(from, to))}%`,
        width: `${(Math.abs(to - from) / span) * 100}%`,
    })

    return (
        <div className={className}>
            <div className="relative h-1.5 w-full rounded-full bg-surface-track">
                {stop !== undefined && (
                    <span
                        aria-hidden
                        className="chart-grow chart-move absolute inset-y-0 bg-negative/35"
                        style={zone(stop, entry)}
                    />
                )}
                {target !== undefined && (
                    <span
                        aria-hidden
                        className="chart-grow chart-move absolute inset-y-0 bg-positive/35"
                        style={zone(entry, target)}
                    />
                )}
                {stop !== undefined && <Marker at={positionOf(stop)} tone="negative" />}
                <Marker at={positionOf(entry)} tone="neutral" />
                {target !== undefined && <Marker at={positionOf(target)} tone="positive" />}
            </div>

            <div className="relative mt-2.5 h-7">
                {stop !== undefined && <Leg at={positionOf(stop)} label="Stop" value={stop} tone="negative" />}
                <Leg at={positionOf(entry)} label="Entry" value={entry} tone="neutral" />
                {target !== undefined && <Leg at={positionOf(target)} label="Target" value={target} tone="positive" />}
            </div>
        </div>
    )
}

function Marker({ at, tone }: { at: number; tone: 'negative' | 'neutral' | 'positive' }) {
    return (
        <span
            aria-hidden
            className={cn(
                'absolute top-1/2 h-3 w-[3px] -translate-x-1/2 -translate-y-1/2 rounded-full',
                tone === 'negative' && 'bg-negative',
                tone === 'positive' && 'bg-positive',
                tone === 'neutral' && 'bg-ink-primary',
            )}
            style={{ left: `${at}%` }}
        />
    )
}

function Leg({
    at,
    label,
    value,
    tone,
}: {
    at: number
    label: string
    value: number
    tone: 'negative' | 'neutral' | 'positive'
}) {
    // Clamp the translate at the edges so end labels stay inside the box.
    const translate = at < 12 ? 'translate-x-0' : at > 88 ? '-translate-x-full' : '-translate-x-1/2'
    return (
        <span className={cn('absolute top-0 flex flex-col gap-0.5 whitespace-nowrap', translate)} style={{ left: `${at}%` }}>
            <span
                className={cn(
                    'font-mono text-[9px] uppercase tracking-[0.1em]',
                    tone === 'negative' && 'text-negative',
                    tone === 'positive' && 'text-positive',
                    tone === 'neutral' && 'text-ink-secondary',
                )}
            >
                {label}
            </span>
            <span className="nums font-mono text-[11px] text-ink-primary">{price(value)}</span>
        </span>
    )
}
