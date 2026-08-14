'use client'

import { useEffect, useState } from 'react'
import { cn } from '@/lib/cn'
import { minutesSinceMidnight } from '@/lib/format'

/**
 * OrderFlowTimeline — the day's order book placed on a real wall-clock axis.
 *
 * This is the one genuinely temporal view the broker payload supports: orders
 * carry `createTime`, so *when* activity clustered is real information, unlike
 * a price sparkline which would have to be invented. Buys and sells occupy
 * separate lanes so one-sided bursts are visible at a glance.
 *
 * Layout note: the lane labels sit in their own column and every positioned
 * element (gridlines, markers, axis ticks) shares one plot-area coordinate
 * space, so percentages line up across all three rows.
 */

const SESSION_OPEN = 9 * 60 + 15 // NSE/BSE equity session
const SESSION_CLOSE = 15 * 60 + 30
const LABEL_COLUMN = 'w-11 flex-shrink-0'
const LANE_HEIGHT = 'h-9'

export interface OrderFlowPoint {
    key: string
    /** Timestamp in any form `parseTimestamp` understands. */
    at?: string | number | null
    lane: 'buy' | 'sell'
    tone: 'positive' | 'negative' | 'warning' | 'neutral'
    /** Hover description, e.g. "RELIANCE · 12 qty · TRADED". */
    title: string
}

type PlacedPoint = OrderFlowPoint & { minutes: number }

const TONE_MARKER: Record<OrderFlowPoint['tone'], string> = {
    positive: 'bg-positive',
    negative: 'bg-negative',
    warning: 'bg-warning',
    neutral: 'bg-ink-tertiary',
}

function clockLabel(minutes: number) {
    return `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(Math.round(minutes % 60)).padStart(2, '0')}`
}

export function OrderFlowTimeline({
    points,
    className,
    emptyLabel = 'No orders placed today',
}: {
    points: OrderFlowPoint[]
    className?: string
    emptyLabel?: string
}) {
    // Read the clock after mount so server and client markup agree.
    const [nowMinutes, setNowMinutes] = useState<number | null>(null)
    useEffect(() => {
        const read = () => {
            const now = new Date()
            setNowMinutes(now.getHours() * 60 + now.getMinutes())
        }
        read()
        const timer = window.setInterval(read, 60_000)
        return () => window.clearInterval(timer)
    }, [])

    const placed = points
        .map((point) => ({ ...point, minutes: minutesSinceMidnight(point.at) }))
        .filter((point): point is PlacedPoint => point.minutes !== null)

    if (!placed.length) {
        return <p className={cn('text-[11px] text-ink-tertiary', className)}>{emptyLabel}</p>
    }

    // Always show the full session; widen only if activity falls outside it.
    const dataMin = Math.min(...placed.map((point) => point.minutes))
    const dataMax = Math.max(...placed.map((point) => point.minutes))
    const start = Math.min(SESSION_OPEN, Math.floor(dataMin / 15) * 15)
    const end = Math.max(SESSION_CLOSE, Math.ceil(dataMax / 15) * 15)
    const span = Math.max(end - start, 1)
    const positionOf = (minutes: number) => ((minutes - start) / span) * 100

    const gridlines: number[] = []
    for (let minute = Math.ceil(start / 60) * 60; minute <= end; minute += 60) gridlines.push(minute)

    const showNow = nowMinutes !== null && nowMinutes >= start && nowMinutes <= end
    const buys = placed.filter((point) => point.lane === 'buy')
    const sells = placed.filter((point) => point.lane === 'sell')

    return (
        <div className={className}>
            <div className="flex">
                {/* Lane labels */}
                <div className={LABEL_COLUMN}>
                    <div className={cn(LANE_HEIGHT, 'flex items-center')}>
                        <span className="dash-label">Buy</span>
                    </div>
                    <div className={cn(LANE_HEIGHT, 'flex items-center border-t border-line')}>
                        <span className="dash-label">Sell</span>
                    </div>
                </div>

                {/* Plot area — the shared coordinate space */}
                <div className="relative min-w-0 flex-1">
                    <div aria-hidden className="absolute inset-0">
                        {gridlines.map((minute) => (
                            <span
                                key={minute}
                                className="absolute inset-y-0 w-px bg-line"
                                style={{ left: `${positionOf(minute)}%` }}
                            />
                        ))}
                        {showNow && (
                            <span
                                className="absolute inset-y-0 w-px bg-accent/60"
                                style={{ left: `${positionOf(nowMinutes)}%` }}
                            />
                        )}
                    </div>
                    <Lane points={buys} positionOf={positionOf} />
                    <Lane points={sells} positionOf={positionOf} className="border-t border-line" />
                </div>
            </div>

            {/* Time axis, sharing the plot area's offset */}
            <div className="flex">
                <div className={LABEL_COLUMN} />
                <div aria-hidden className="relative h-4 min-w-0 flex-1">
                    {gridlines.map((minute, index) => (
                        <span
                            key={minute}
                            className={cn(
                                'nums absolute top-1 -translate-x-1/2 font-mono text-[9px] text-ink-tertiary',
                                index % 2 === 1 && 'hidden sm:inline',
                            )}
                            style={{ left: `${positionOf(minute)}%` }}
                        >
                            {clockLabel(minute)}
                        </span>
                    ))}
                </div>
            </div>

            <p className="sr-only">
                {placed.length} orders placed between {clockLabel(dataMin)} and {clockLabel(dataMax)}:{' '}
                {buys.length} buy, {sells.length} sell.
            </p>
        </div>
    )
}

function Lane({
    points,
    positionOf,
    className,
}: {
    points: PlacedPoint[]
    positionOf: (minutes: number) => number
    className?: string
}) {
    return (
        <div className={cn('relative', LANE_HEIGHT, className)}>
            {points.map((point) => (
                <span
                    key={point.key}
                    title={point.title}
                    className={cn(
                        'absolute top-1/2 h-[7px] w-[7px] -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-panel',
                        TONE_MARKER[point.tone],
                    )}
                    style={{ left: `${positionOf(point.minutes)}%` }}
                />
            ))}
            {!points.length && (
                <span className="absolute top-1/2 left-0 -translate-y-1/2 font-mono text-[9px] text-ink-tertiary">
                    None
                </span>
            )}
        </div>
    )
}
