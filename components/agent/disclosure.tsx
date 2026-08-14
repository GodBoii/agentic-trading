'use client'

import { useId, useState, type ReactNode } from 'react'
import { cn } from '@/lib/cn'
import { ChevronDown } from '@/components/ui/icons'

/**
 * Disclosure — a labelled expandable region.
 *
 * Replaces the bare `<details><summary>` + `<pre>` pattern used for tool
 * arguments, raw metadata and structured input. `<details>` gave no control
 * over the marker, no transition, and no way to show a size hint before the
 * reader commits to expanding a 40kb payload.
 */
export function Disclosure({
    label,
    hint,
    children,
    defaultOpen = false,
    className,
}: {
    label: string
    /** Shown next to the label, e.g. "12 keys" or "8.2k chars". */
    hint?: string
    children: ReactNode
    defaultOpen?: boolean
    className?: string
}) {
    const [open, setOpen] = useState(defaultOpen)
    const id = useId()

    return (
        <div className={cn('rounded-xl border border-line bg-panel-inset', className)}>
            <button
                type="button"
                aria-expanded={open}
                aria-controls={id}
                onClick={() => setOpen((current) => !current)}
                className="flex w-full items-center gap-2 px-3.5 py-2.5 text-left transition-colors hover:bg-white/[0.02]"
            >
                <ChevronDown
                    size={13}
                    className={cn(
                        'flex-shrink-0 text-ink-tertiary transition-transform duration-150',
                        open && 'rotate-180',
                    )}
                />
                <span className="dash-label flex-1">{label}</span>
                {hint && <span className="nums font-mono text-[9px] text-ink-tertiary">{hint}</span>}
            </button>
            {open && (
                <div id={id} className="border-t border-line px-3.5 py-3">
                    {children}
                </div>
            )}
        </div>
    )
}

/**
 * Monospace payload viewer. Caps its own height and scrolls, so a large tool
 * result cannot push the rest of the timeline off screen.
 */
export function CodeBlock({ children, maxHeight = 260 }: { children: string; maxHeight?: number }) {
    return (
        <pre
            className="overflow-auto whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-ink-secondary"
            style={{ maxHeight }}
        >
            {children}
        </pre>
    )
}

/**
 * Long prose that collapses to a readable height with a fade, using the
 * existing `.clamp-region` mechanics.
 */
export function ClampedRegion({
    children,
    expandLabel = 'Show full output',
    collapseLabel = 'Collapse',
}: {
    children: ReactNode
    expandLabel?: string
    collapseLabel?: string
}) {
    const [clamped, setClamped] = useState(true)
    return (
        <div className="clamp-region" data-clamped={clamped}>
            <div className="clamp-content">{children}</div>
            <button type="button" className="clamp-toggle" onClick={() => setClamped((current) => !current)}>
                {clamped ? expandLabel : collapseLabel}
            </button>
        </div>
    )
}
