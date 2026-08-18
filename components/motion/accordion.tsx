'use client'

import { useId, useState, type ReactNode } from 'react'
import { cn } from '@/lib/cn'

/**
 * Recipe 21 — accordion expand.
 *
 * Height animates through `grid-template-rows: 0fr → 1fr`, so content of any
 * size animates cleanly with no JS measurement and no `max-height` guess that
 * clips long payloads. Symmetric at 250ms: expanding and collapsing are one
 * reversible motion.
 *
 * Two structural rules are load-bearing:
 *   1. The panel needs both elements — the grid track and an inner child that
 *      clips its own overflow. A `0fr` track can only collapse a child that
 *      hides what spills out.
 *   2. Padding goes on the inner element, never on the track. Padding on a
 *      `0fr` row leaves a residual height strip, so the panel never fully
 *      closes and every collapsed item keeps a few stubborn pixels.
 */

/** Symmetric chevron, flipped rather than path-morphed. */
export function AccordionChevron({ size = 15, className }: { size?: number; className?: string }) {
    return (
        <span className={cn('t-acc-chevron', className)} aria-hidden>
            <svg width={size} height={size} viewBox="0 0 16 16" fill="none">
                {/* Symmetric about the viewBox centre (y = 8) so scaleY(-1)
                    maps the "v" exactly onto the "^". */}
                <path
                    d="M4 6L8 10L12 6"
                    stroke="currentColor"
                    strokeWidth={1.6}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                />
            </svg>
        </span>
    )
}

/**
 * Uncontrolled disclosure. `Accordion` owns its own open state; use
 * `AccordionShell` when the parent needs to coordinate a group.
 */
export function Accordion({
    header,
    children,
    defaultOpen = false,
    className,
    headerClassName,
    panelClassName,
}: {
    /** Rendered inside the trigger button. The chevron is appended. */
    header: ReactNode
    children: ReactNode
    defaultOpen?: boolean
    className?: string
    headerClassName?: string
    panelClassName?: string
}) {
    const [open, setOpen] = useState(defaultOpen)
    return (
        <AccordionShell
            open={open}
            onToggle={() => setOpen((current) => !current)}
            header={header}
            className={className}
            headerClassName={headerClassName}
            panelClassName={panelClassName}
        >
            {children}
        </AccordionShell>
    )
}

/** Controlled disclosure, for accordion groups with one-open-at-a-time. */
export function AccordionShell({
    open,
    onToggle,
    header,
    children,
    className,
    headerClassName,
    panelClassName,
    /** Set when the trigger is not a plain button context. */
    ariaLabel,
}: {
    open: boolean
    onToggle: () => void
    header: ReactNode
    children: ReactNode
    className?: string
    headerClassName?: string
    panelClassName?: string
    ariaLabel?: string
}) {
    const panelId = useId()

    return (
        <div className={cn('t-acc', className)} data-open={open}>
            <button
                type="button"
                aria-expanded={open}
                aria-controls={panelId}
                aria-label={ariaLabel}
                onClick={onToggle}
                className={cn(
                    't-acc-head flex w-full items-center gap-3 text-left',
                    headerClassName,
                )}
            >
                {header}
            </button>
            <div id={panelId} className="t-acc-panel" role="region" aria-hidden={!open}>
                {/* Padding belongs here, not on `.t-acc-panel`. */}
                <div className={cn('t-acc-panel-inner', panelClassName)}>{children}</div>
            </div>
        </div>
    )
}
