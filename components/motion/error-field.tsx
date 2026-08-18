'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { cn } from '@/lib/cn'
import { forceReflow, motionMs, prefersReducedMotion } from './tokens'

/**
 * Recipe 12 — error state shake.
 *
 * The field shakes left/right with an overshoot, its border switches to the
 * error tone, and a message reveals beneath. After a hold long enough to read
 * the message, border and message fade back to neutral. Typing cancels the
 * revert immediately, so the user is never shaking at a value they are
 * already correcting.
 *
 * Three classes, kept deliberately orthogonal:
 *   - `.is-error` on the wrapper drives the message (the message lives there)
 *   - `.is-error` on the field drives the border (the field owns the border)
 *   - `.is-shaking` on the field drives the motion, separate from the tone
 *
 * Merging the last two would make the shake un-replayable: removing and
 * re-adding a single combined class to restart the animation would also
 * flicker the whole error treatment off and on in the same tick.
 *
 * This replaces the static red panel that both auth screens rendered above
 * their form. A message that simply appears is easy to miss when the eye is
 * still on the field that caused it; the shake puts the feedback where the
 * problem is.
 */
export function useErrorShake<T extends HTMLElement = HTMLDivElement>() {
    const fieldRef = useRef<T | null>(null)
    const [errored, setErrored] = useState(false)
    const [shaking, setShaking] = useState(false)
    const shakeTimer = useRef<number | null>(null)
    const revertTimer = useRef<number | null>(null)

    const clearTimers = useCallback(() => {
        if (shakeTimer.current) window.clearTimeout(shakeTimer.current)
        if (revertTimer.current) window.clearTimeout(revertTimer.current)
        shakeTimer.current = null
        revertTimer.current = null
    }, [])

    /** Show the error tone and replay the shake. Safe to call repeatedly. */
    const trigger = useCallback(() => {
        clearTimers()
        setErrored(true)

        if (prefersReducedMotion()) return

        // Replay from a clean baseline. Without the reflow between removing
        // and re-adding the class, a second failed submit does not shake.
        setShaking(false)
        forceReflow(fieldRef.current)
        setShaking(true)

        const shakeMs = motionMs('--shake-dur-a', 80) * 2 + motionMs('--shake-dur-b', 60) * 2
        shakeTimer.current = window.setTimeout(() => setShaking(false), shakeMs + 20)

        // Auto-revert, so a stale error does not sit on screen indefinitely.
        revertTimer.current = window.setTimeout(
            () => setErrored(false),
            shakeMs + motionMs('--revert-hold', 3000),
        )
    }, [clearTimers])

    /** Call from the field's `onChange`: correcting cancels the error. */
    const clear = useCallback(() => {
        clearTimers()
        setErrored(false)
        setShaking(false)
    }, [clearTimers])

    useEffect(() => clearTimers, [clearTimers])

    return {
        errored,
        shaking,
        trigger,
        clear,
        /** Attach to the element that owns the visible border. */
        fieldRef,
        /** Class for the wrapper that contains the message. */
        wrapClass: cn('t-input-wrap', errored && 'is-error'),
        /** Class for the bordered field itself. */
        fieldClass: cn('t-input', errored && 'is-error', shaking && 'is-shaking'),
    }
}

/**
 * The revealing message. Stays mounted so its opacity can transition — and so
 * its height does not pop the form's layout when an error appears.
 */
export function ErrorMessage({
    children,
    id,
    className,
}: {
    children?: string | null
    id?: string
    className?: string
}) {
    return (
        <p
            id={id}
            role="alert"
            className={cn('t-error-msg mt-2 text-[11px] leading-relaxed text-negative', className)}
        >
            {/* A non-breaking space holds the line so the field below does not
                shift when the message arrives. */}
            {children || '\u00a0'}
        </p>
    )
}
