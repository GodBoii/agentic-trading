'use client'

import { useState, type ReactNode } from 'react'
import { cn } from '@/lib/cn'
import { AccordionChevron, AccordionShell } from '@/components/motion/accordion'

/**
 * Disclosure — a labelled expandable region.
 *
 * Replaces the bare `<details><summary>` + `<pre>` pattern used for tool
 * arguments, raw metadata and structured input. `<details>` gave no control
 * over the marker, no transition, and no way to show a size hint before the
 * reader commits to expanding a 40kb payload.
 *
 * Motion (recipe 21, accordion). Two things changed from the previous version:
 *
 *   - The panel now animates open through `grid-template-rows: 0fr → 1fr`
 *     instead of being conditionally mounted. Conditional mounting meant a
 *     40kb tool result appeared in one frame and shoved the rest of the
 *     timeline down the page — on a live event feed, that is disorienting
 *     because the reader may be mid-sentence somewhere below it.
 *
 *   - The chevron flips vertically rather than rotating 180°. A rotation
 *     travels through a sideways position that means nothing; the flip passes
 *     through a flat line, which reads as the marker inverting. It also avoids
 *     SVG `d:` path morphing, which only animates in Chromium.
 *
 * The payload stays mounted while collapsed, which is what allows the height to
 * animate at all — there is nothing to grow toward if the content does not
 * exist yet.
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

    return (
        <AccordionShell
            open={open}
            onToggle={() => setOpen((current) => !current)}
            className={cn('overflow-hidden rounded-xl border border-line bg-panel-inset', className)}
            headerClassName="px-3.5 py-2.5"
            header={
                <>
                    <AccordionChevron size={13} className="flex-shrink-0 text-ink-tertiary" />
                    <span className="dash-label flex-1">{label}</span>
                    {hint && <span className="nums font-mono text-[9px] text-ink-tertiary">{hint}</span>}
                </>
            }
            panelClassName="border-t border-line px-3.5 py-3"
        >
            {children}
        </AccordionShell>
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
 * Long prose that collapses to a readable height with a fade.
 *
 * Distinct from `Disclosure`: the content is always partly visible, so this is
 * a clamp rather than a reveal. The height change is not animated on purpose —
 * expanding a 900-character block tweens through a lot of reflow, and the fade
 * edge already signals that there is more.
 */
export function ClampedRegion({
    children,
    expandLabel = 'Show full output',
    collapseLabel = 'Collapse',
    surface,
}: {
    children: ReactNode
    expandLabel?: string
    collapseLabel?: string
    /** Match the fade to the surface underneath, or a grey band appears. */
    surface?: 'panel' | 'inset'
}) {
    const [clamped, setClamped] = useState(true)
    return (
        <div className="clamp-region" data-clamped={clamped} data-surface={surface}>
            <div className="clamp-content">{children}</div>
            <button
                type="button"
                className="clamp-toggle t-press"
                onClick={() => setClamped((current) => !current)}
            >
                {clamped ? expandLabel : collapseLabel}
            </button>
        </div>
    )
}
