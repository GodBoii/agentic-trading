'use client'

import { useEffect, useRef, useState, type ReactNode } from 'react'
import { cn } from '@/lib/cn'
import { motionMs } from './tokens'

export type DropdownOrigin =
    | 'top-left'
    | 'top-center'
    | 'top-right'
    | 'bottom-left'
    | 'bottom-center'
    | 'bottom-right'

/**
 * Recipe 05 — menu dropdown.
 *
 * An anchored surface that grows out of its trigger: 250ms open from 0.97,
 * 150ms close to 0.99. `data-origin` sets the transform origin so the growth
 * actually starts at the trigger's corner rather than the panel's centre —
 * that correspondence is the whole reason a dropdown reads as belonging to
 * the thing that opened it.
 *
 * Distinct from `Modal`: this is anchored and non-blocking. If a surface has
 * no anchor and demands a response before continuing, it is a modal.
 */
export function Dropdown({
    open,
    origin = 'top-right',
    children,
    className,
    id,
    role = 'menu',
    ariaLabel,
    ariaLabelledBy,
}: {
    open: boolean
    origin?: DropdownOrigin
    children: ReactNode
    className?: string
    id?: string
    role?: 'menu' | 'listbox' | 'dialog' | 'none'
    /**
     * Required in practice for `role="dialog"`: an unnamed dialog is announced
     * only as "dialog", so the user is told a surface opened but not what it is.
     */
    ariaLabel?: string
    ariaLabelledBy?: string
}) {
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
            // Clearing `.is-closing` is what lets the next open start from the
            // pre-open scale instead of the closing one.
            setClosing(false)
            setPresent(false)
        }, motionMs('--dropdown-close-dur', 150))

        return () => {
            if (timer.current) window.clearTimeout(timer.current)
        }
    }, [open, present])

    if (!present) return null

    return (
        <div
            id={id}
            role={role === 'none' ? undefined : role}
            aria-label={ariaLabel}
            aria-labelledby={ariaLabelledBy}
            data-origin={origin}
            className={cn('t-dropdown', open && !closing && 'is-open', closing && 'is-closing', className)}
        >
            {children}
        </div>
    )
}

/**
 * Open state plus dismissal for an anchored surface: outside click, Escape,
 * and focus leaving the anchor entirely.
 *
 * `pointerdown` rather than `click` so the menu closes on press instead of
 * waiting for release — a menu that lingers through a drag feels stuck.
 */
export function useDropdown<T extends HTMLElement = HTMLDivElement>() {
    const [open, setOpen] = useState(false)
    const anchor = useRef<T | null>(null)

    useEffect(() => {
        if (!open) return

        const onPointerDown = (event: PointerEvent) => {
            if (!anchor.current?.contains(event.target as Node)) setOpen(false)
        }
        const onKeyDown = (event: KeyboardEvent) => {
            if (event.key === 'Escape') setOpen(false)
        }
        const onFocusIn = (event: FocusEvent) => {
            if (!anchor.current?.contains(event.target as Node)) setOpen(false)
        }

        document.addEventListener('pointerdown', onPointerDown)
        document.addEventListener('keydown', onKeyDown)
        document.addEventListener('focusin', onFocusIn)
        return () => {
            document.removeEventListener('pointerdown', onPointerDown)
            document.removeEventListener('keydown', onKeyDown)
            document.removeEventListener('focusin', onFocusIn)
        }
    }, [open])

    return { open, setOpen, toggle: () => setOpen((current) => !current), anchor }
}
