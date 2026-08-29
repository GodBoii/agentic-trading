'use client'

import { useEffect, useRef, useState } from 'react'
import { cn } from '@/lib/cn'
import { Alert } from '@/components/ui/icons'
import { motionMs } from './tokens'
import { SuccessCheck } from './success-check'

export type ToastTone = 'success' | 'error' | 'neutral'

export interface ToastMessage {
    tone: ToastTone
    message: string
}

/**
 * Recipe 22 — toast open / close.
 *
 * Rises into view on the slower open clock (350ms) and leaves on the faster
 * close clock (250ms), so arriving feels deliberate and dismissal feels
 * snappy. Replaces the `framer-motion` `AnimatePresence` block on the
 * dashboard, whose exit ran at the same speed as its entrance.
 *
 * Docked below the sticky product header, so it descends from the top edge
 * rather than rising from the bottom of the viewport — a transient
 * confirmation should appear next to the thing it is confirming, not travel
 * the height of the page to get there.
 */
const TONE_SURFACE: Record<ToastTone, string> = {
    success: 'tint-positive border-positive/25 text-positive',
    error: 'tint-negative border-negative/25 text-negative',
    neutral: 'border-line bg-panel text-ink-secondary',
}

export function Toast({
    toast,
    onDismiss,
}: {
    /** `null` plays the exit and then unmounts. */
    toast: ToastMessage | null
    onDismiss?: () => void
}) {
    /** Held through the exit so the close is actually visible. */
    const [shown, setShown] = useState<ToastMessage | null>(toast)
    const [open, setOpen] = useState(false)
    const timer = useRef<number | null>(null)

    useEffect(() => {
        if (timer.current) window.clearTimeout(timer.current)

        if (toast) {
            setShown(toast)
            // One frame so the pre-open transform is painted first; setting
            // both in the same commit gives the transition nothing to
            // interpolate from and the toast simply appears.
            const frame = requestAnimationFrame(() => setOpen(true))
            return () => cancelAnimationFrame(frame)
        }

        setOpen(false)
        timer.current = window.setTimeout(() => setShown(null), motionMs('--toast-close', 250))
        return () => {
            if (timer.current) window.clearTimeout(timer.current)
        }
    }, [toast])

    if (!shown) return null

    return (
        <div
            role="status"
            aria-live="polite"
            data-from="top"
            className={cn(
                // Inset from the right on desktop; full width less the gutters
                // on a phone, where a 300px card pinned to one edge leaves the
                // message wrapping in a column half the screen wide.
                't-toast fixed inset-x-4 top-[68px] z-[var(--z-toast)] flex items-center gap-2.5 rounded-xl border px-3.5 py-3 text-[12px] shadow-pop backdrop-blur-xl sm:inset-x-auto sm:right-6 sm:max-w-[380px]',
                TONE_SURFACE[shown.tone],
                open && 'is-open',
            )}
        >
            {shown.tone === 'success' ? (
                // The check draws itself as the toast lands, so the
                // confirmation reads as earned rather than pre-printed.
                <SuccessCheck size={15} play={open} className="flex-shrink-0" />
            ) : shown.tone === 'error' ? (
                <Alert size={14} className="flex-shrink-0" />
            ) : null}
            <span className="min-w-0">{shown.message}</span>
            {onDismiss && (
                <button
                    type="button"
                    onClick={onDismiss}
                    aria-label="Dismiss"
                    className="t-press ml-1 flex-shrink-0 rounded-md px-1 text-current opacity-50 transition-opacity duration-150 hover:opacity-100"
                >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" aria-hidden>
                        <path d="M6 6l12 12M18 6L6 18" />
                    </svg>
                </button>
            )}
        </div>
    )
}

/**
 * Auto-dismissing toast state.
 *
 * `hold` is the read time, not part of the animation — the exit clock is
 * owned by the recipe. A toast is transient by definition; anything the user
 * must acknowledge belongs in a `Notice` or a `Modal`.
 */
export function useToast(hold = 6000) {
    const [toast, setToast] = useState<ToastMessage | null>(null)
    const timer = useRef<number | null>(null)

    const show = (next: ToastMessage) => {
        setToast(next)
        if (timer.current) window.clearTimeout(timer.current)
        timer.current = window.setTimeout(() => setToast(null), hold)
    }

    const dismiss = () => {
        if (timer.current) window.clearTimeout(timer.current)
        setToast(null)
    }

    useEffect(
        () => () => {
            if (timer.current) window.clearTimeout(timer.current)
        },
        [],
    )

    return { toast, show, dismiss }
}
