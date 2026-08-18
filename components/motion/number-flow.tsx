'use client'

import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { cn } from '@/lib/cn'
import { forceReflow, motionMs, motionNum, prefersReducedMotion } from './tokens'

const useIsomorphicLayoutEffect = typeof window === 'undefined' ? useEffect : useLayoutEffect

/**
 * Recipe 02 — number pop-in.
 *
 * A figure that has just changed re-enters character by character from below
 * with a 2px blur. The two trailing characters ride 1× and 2× the stagger
 * behind the rest, so decimals feel alive without the whole number looking
 * like it exploded.
 *
 * This is the right treatment for live broker figures — balances, P&L,
 * exposure. It marks *that a value moved* without stealing attention, which
 * matters on a screen where five numbers can update at once. Reach for
 * `SpinningCounter` instead only when a change is genuinely an event.
 *
 * The whole formatted string is animated, currency glyph and separators
 * included, because splitting on digits alone leaves "₹" and "," hanging
 * motionless inside a moving number.
 */
export function NumberFlow({
    value,
    className,
}: {
    /** The already-formatted display string, e.g. `money(x)`. */
    value: string
    className?: string
}) {
    const ref = useRef<HTMLSpanElement | null>(null)
    const [animating, setAnimating] = useState(false)
    /** Skips the animation on first paint — nothing has "changed" yet. */
    const mounted = useRef(false)
    const previous = useRef(value)
    const timer = useRef<number | null>(null)

    useIsomorphicLayoutEffect(() => {
        if (!mounted.current) {
            mounted.current = true
            previous.current = value
            return
        }
        if (value === previous.current) return
        previous.current = value
        if (prefersReducedMotion()) return

        const node = ref.current
        if (!node) return

        // Replay from a clean baseline: drop the class, reflow, re-add.
        setAnimating(false)
        node.classList.remove('is-animating')
        forceReflow(node)
        setAnimating(true)

        if (timer.current) window.clearTimeout(timer.current)
        // Release `will-change` once the animation is done rather than
        // leaving every figure on the page permanently promoted.
        const total = motionMs('--digit-dur', 500) + motionMs('--digit-stagger', 70) * 2
        timer.current = window.setTimeout(() => setAnimating(false), total + 40)
    }, [value])

    useEffect(
        () => () => {
            if (timer.current) window.clearTimeout(timer.current)
        },
        [],
    )

    const characters = Array.from(value)

    return (
        <span
            ref={ref}
            className={cn('t-digit-group', animating && 'is-animating', className)}
            // The split into per-character spans is decoration; assistive tech
            // should read the value as one string.
            aria-label={value}
        >
            {characters.map((character, index) => {
                const fromEnd = characters.length - index
                const stagger = fromEnd === 2 ? '1' : fromEnd === 1 ? '2' : undefined
                return (
                    <span
                        key={`${index}-${character}`}
                        className="t-digit"
                        data-stagger={stagger}
                        aria-hidden
                    >
                        {/* A literal space would collapse between inline-blocks. */}
                        {character === ' ' ? '\u00a0' : character}
                    </span>
                )
            })}
        </span>
    )
}

/**
 * Recipe 26 — spinning counter.
 *
 * Slot-machine digit reels with a vertical motion streak. Each digit is a
 * clipped column holding 0-9; the strip translates up through several full
 * spins before landing, with a per-column stagger so the reels settle left
 * to right.
 *
 * Reserved for counts that are an *event* rather than a running value — the
 * archive totals on the Trades screen, which change once when the page loads
 * and are the headline of that screen. Applying this to a live price would
 * be exhausting.
 *
 * The blur is applied as a scaled vertical `blur()` on the strip while it
 * moves and decays to zero as it lands. A uniform CSS blur would smear the
 * digits sideways too, which reads as being out of focus rather than moving.
 */
const SPINS = 2

export function SpinningCounter({
    value,
    className,
}: {
    /** Non-negative integer. Formatting/separators are not supported here. */
    value: number
    className?: string
}) {
    const safe = Number.isFinite(value) ? Math.max(0, Math.round(value)) : 0
    const digits = String(safe).split('')
    const [landed, setLanded] = useState(false)
    const previous = useRef<string | null>(null)

    useEffect(() => {
        const next = String(safe)
        if (previous.current === next) return
        previous.current = next

        if (prefersReducedMotion()) {
            setLanded(true)
            return
        }

        setLanded(false)
        const frame = requestAnimationFrame(() => setLanded(true))
        return () => cancelAnimationFrame(frame)
    }, [safe])

    const cell = motionNum('--reel-cell', 30)
    const duration = motionMs('--reel-dur', 1400)
    const stagger = motionMs('--reel-stagger', 90)

    return (
        <span className={cn('t-reel', className)} aria-label={String(safe)}>
            {digits.map((digit, column) => {
                const target = Number(digit)
                // Spin through whole revolutions before stopping on the digit.
                const offset = landed ? (SPINS * 10 + target) * cell : 0
                const delay = column * stagger
                return (
                    <span className="t-reel-col" key={column} aria-hidden style={{ width: '1ch' }}>
                        <span
                            className="t-reel-strip"
                            style={{
                                transform: `translateY(-${offset}px)`,
                                transition: `transform ${duration}ms var(--reel-ease) ${delay}ms, filter ${duration}ms var(--reel-ease) ${delay}ms`,
                                filter: landed ? 'blur(0px)' : undefined,
                            }}
                        >
                            {/* Enough cells for the full spin plus the landing digit. */}
                            {Array.from({ length: SPINS * 10 + 10 }, (_, index) => (
                                <span className="t-reel-digit" key={index}>
                                    {index % 10}
                                </span>
                            ))}
                        </span>
                    </span>
                )
            })}
        </span>
    )
}
