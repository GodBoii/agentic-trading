'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { cn } from '@/lib/cn'
import { motionMs } from './tokens'

/**
 * Recipe 06 — modal open / close.
 *
 * A centred surface that scales up from 0.96, and dips back to 0.96 on the
 * way out over a shorter clock: 250ms open, 150ms close. Opening is an
 * invitation; closing should get out of the way.
 *
 * The `.is-closing` class must be removed once the exit has played. Without
 * that cleanup the element rests at the *closing* scale, so the next open
 * starts from the wrong place and the entrance visibly jumps.
 */
export function useModal(open: boolean) {
    /** Kept mounted for the length of the exit so the close can be seen. */
    const [present, setPresent] = useState(open)
    const [closing, setClosing] = useState(false)
    const timer = useRef<number | null>(null)

    useEffect(() => {
        if (timer.current) window.clearTimeout(timer.current)

        if (open) {
            setClosing(false)
            setPresent(true)
            return
        }

        if (!present) return

        setClosing(true)
        timer.current = window.setTimeout(() => {
            // Order matters: drop `.is-closing` as the node unmounts so a
            // reopen starts from the resting pre-open scale.
            setClosing(false)
            setPresent(false)
        }, motionMs('--modal-close-dur', 150))

        return () => {
            if (timer.current) window.clearTimeout(timer.current)
        }
    }, [open, present])

    return { present, open: open && !closing, closing }
}

/**
 * Dialog with a scrim, focus containment and Escape-to-dismiss.
 *
 * Hand-rolled rather than pulled from a dialog library: the project has no
 * component-primitive dependency, and this needs exactly three behaviours —
 * dismiss, restore focus, and trap Tab.
 */
export function Modal({
    open,
    onClose,
    children,
    labelledBy,
    describedBy,
    className,
}: {
    open: boolean
    onClose: () => void
    children: React.ReactNode
    labelledBy?: string
    describedBy?: string
    className?: string
}) {
    const { present, open: shown } = useModal(open)
    const surface = useRef<HTMLDivElement | null>(null)
    const restoreTo = useRef<HTMLElement | null>(null)

    // Remember what had focus so it can be handed back on dismissal —
    // otherwise focus falls to the top of the document and keyboard users
    // lose their position entirely.
    useEffect(() => {
        if (!open) return
        restoreTo.current = document.activeElement as HTMLElement | null
        return () => restoreTo.current?.focus?.()
    }, [open])

    // Move focus into the dialog once it is mounted and painted.
    useEffect(() => {
        if (!shown) return
        const frame = requestAnimationFrame(() => {
            const node = surface.current
            if (!node) return
            const focusable = node.querySelector<HTMLElement>(
                'button:not([disabled]), [href], input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])',
            )
            ;(focusable || node).focus()
        })
        return () => cancelAnimationFrame(frame)
    }, [shown])

    const onKeyDown = useCallback(
        (event: React.KeyboardEvent) => {
            if (event.key === 'Escape') {
                event.stopPropagation()
                onClose()
                return
            }
            if (event.key !== 'Tab') return

            const node = surface.current
            if (!node) return
            const focusable = Array.from(
                node.querySelectorAll<HTMLElement>(
                    'button:not([disabled]), [href], input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])',
                ),
            ).filter((element) => element.offsetParent !== null)
            if (!focusable.length) return

            const first = focusable[0]
            const last = focusable[focusable.length - 1]
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault()
                last.focus()
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault()
                first.focus()
            }
        },
        [onClose],
    )

    if (!present) return null

    return (
        <div className="fixed inset-0 z-[100] grid place-items-center px-5" onKeyDown={onKeyDown}>
            <div
                className={cn('t-modal-scrim absolute inset-0 bg-black/70 backdrop-blur-sm', shown && 'is-open')}
                onClick={onClose}
                aria-hidden
            />
            <div
                ref={surface}
                role="dialog"
                aria-modal="true"
                aria-labelledby={labelledBy}
                aria-describedby={describedBy}
                tabIndex={-1}
                className={cn(
                    't-modal relative w-full max-w-sm rounded-2xl border border-line bg-panel shadow-[0_28px_80px_-24px_rgba(0,0,0,0.9)] outline-none',
                    shown && 'is-open',
                    !shown && 'is-closing',
                    className,
                )}
            >
                {children}
            </div>
        </div>
    )
}
