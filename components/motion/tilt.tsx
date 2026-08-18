'use client'

import { useCallback, useRef, type ReactNode } from 'react'
import { cn } from '@/lib/cn'
import { prefersReducedMotion } from './tokens'

/** Peak lean at the card's edges, in degrees. 10–16 reads as subtle. */
const MAX_TILT = 11

/**
 * Recipe 19 — card hover tilt.
 *
 * The card leans toward the pointer in 3D with a soft glare tracking the
 * cursor across it. While the pointer moves the card follows on a short
 * clock; on leave it eases back to flat over a full second, so the release
 * feels like weight settling rather than a snap.
 *
 * The pointer is tracked on the flat *outer* wrapper, which never transforms.
 * Tracking the rotating card itself makes its edges slip out from under the
 * cursor near the borders, so `pointerleave` fires mid-hover and the effect
 * flickers on and off.
 *
 * Reserved for the landing page's feature tiles — surfaces whose job is to
 * feel tangible. Deliberately not applied to dashboard panels: tilting a
 * table of live P&L figures makes them harder to read, which is the opposite
 * of what that screen is for.
 */
export function Tilt({
    children,
    className,
    cardClassName,
    glare = true,
}: {
    children: ReactNode
    className?: string
    cardClassName?: string
    glare?: boolean
}) {
    const outer = useRef<HTMLDivElement | null>(null)
    const card = useRef<HTMLDivElement | null>(null)

    const reset = useCallback(() => {
        outer.current?.classList.remove('is-hover')
        const node = card.current
        if (!node) return
        node.classList.remove('is-tilting')
        node.style.setProperty('--tilt-rx', '0deg')
        node.style.setProperty('--tilt-ry', '0deg')
    }, [])

    const track = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
        // Checked in JS as well as CSS: under reduced motion the pointer
        // should not be tracked at all, not merely tweened to zero.
        if (prefersReducedMotion()) return
        const host = outer.current
        const node = card.current
        if (!host || !node) return

        const rect = host.getBoundingClientRect()
        const px = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width))
        const py = Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height))

        host.classList.add('is-hover')
        node.classList.add('is-tilting')
        node.style.setProperty('--tilt-ry', `${((px - 0.5) * MAX_TILT).toFixed(2)}deg`)
        node.style.setProperty('--tilt-rx', `${((0.5 - py) * MAX_TILT).toFixed(2)}deg`)
        node.style.setProperty('--tilt-gx', `${(px * 100).toFixed(1)}%`)
        node.style.setProperty('--tilt-gy', `${(py * 100).toFixed(1)}%`)
    }, [])

    const onPointerDown = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
        // Touch and pen: capture so a drag keeps targeting the card even if
        // the finger drifts past its edge.
        if (event.pointerType !== 'mouse') {
            try {
                outer.current?.setPointerCapture(event.pointerId)
            } catch {
                /* capture is best-effort */
            }
        }
    }, [])

    return (
        <div
            ref={outer}
            className={cn('t-tilt', className)}
            onPointerDown={onPointerDown}
            onPointerMove={track}
            onPointerUp={reset}
            onPointerCancel={reset}
            onPointerLeave={(event) => {
                // Touch already reset on pointerup.
                if (event.pointerType === 'mouse') reset()
            }}
        >
            <div ref={card} className={cn('t-tilt-card', cardClassName)}>
                {children}
                {glare && <div className="t-tilt-glare" aria-hidden />}
            </div>
        </div>
    )
}
