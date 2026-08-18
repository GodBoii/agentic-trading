'use client'

import { useCallback, useRef } from 'react'
import { motionEase, motionNum } from './tokens'

/**
 * Recipe 11 — hover group with distance falloff.
 *
 * Hovering one item lifts it, lifts its neighbours by a power falloff, and
 * springs the whole row back on leave. The falloff is what makes a row feel
 * like a connected physical object instead of a set of independent buttons.
 *
 * The direction-aware easing is the load-bearing detail, and it cannot be
 * expressed in CSS alone. Both the lift and the return animate the same
 * property — `transform` — so a single `transition-timing-function` declared
 * in CSS would apply to both directions. The browser uses whichever timing
 * function is current at the moment a transitionable property changes, so
 * writing it inline *immediately before* mutating the variables gives a clean
 * ease on the way up and a bouncy overshoot on the way back, with no second
 * class and no duplicate transition declaration.
 *
 * Applied to the agent roster: a run's agents are peers, and combing across
 * them signals that.
 */
export function useHoverGroup<T extends HTMLElement = HTMLElement>() {
    const root = useRef<T | null>(null)

    const apply = useCallback((activeIndex: number | null, phase: 'in' | 'out') => {
        const host = root.current
        if (!host) return

        const items = Array.from(host.querySelectorAll<HTMLElement>('.t-avatar'))
        if (!items.length) return

        const lift = motionNum('--avatar-lift', -4)
        const falloff = motionNum('--avatar-falloff', 0.45)
        const scale = motionNum('--avatar-scale', 1.05)
        const timing =
            phase === 'out'
                ? motionEase('--avatar-ease-out', 'cubic-bezier(0.34, 3.85, 0.64, 1)')
                : motionEase('--avatar-ease-in', 'cubic-bezier(0.22, 1, 0.36, 1)')

        items.forEach((element, index) => {
            // Written BEFORE the variable mutation below — see the note above.
            element.style.transitionTimingFunction = timing

            if (activeIndex === null) {
                element.style.setProperty('--shift', '0px')
                element.style.setProperty('--scale-active', '1')
                return
            }

            const distance = Math.abs(index - activeIndex)
            element.style.setProperty('--shift', `${(lift * Math.pow(falloff, distance)).toFixed(3)}px`)
            element.style.setProperty('--scale-active', index === activeIndex ? String(scale) : '1')
        })
    }, [])

    return {
        /** Spread onto the container that wraps the `.t-avatar` items. */
        groupProps: {
            ref: root,
            onMouseLeave: () => apply(null, 'out'),
        },
        /** Spread onto each item, which must also carry `.t-avatar`. */
        itemProps: (index: number) => ({
            className: 't-avatar',
            onMouseEnter: () => apply(index, 'in'),
        }),
    }
}
