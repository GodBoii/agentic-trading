'use client'

import { useRef, useState } from 'react'
import { cn } from '@/lib/cn'

/**
 * Recipe 27 — toggle.
 *
 * The thumb travels the track with a two-step overshoot: past the end, back,
 * settle. The track colour cross-fades on its own clock so the two do not
 * move as one block.
 *
 * `.is-init` is added on first interaction, and that guard matters: without
 * it the "off" keyframes are live at mount, so every switch on the page plays
 * its return bounce once on load.
 *
 * The thumb also translates rather than animating `left`, which is what the
 * previous `.dash-toggle` did — `left` is a layout property, so each frame of
 * that animation forced a reflow.
 */
export function Toggle({
    checked,
    onChange,
    label,
    disabled,
    className,
}: {
    checked: boolean
    onChange: (next: boolean) => void
    /** Required: a bare switch with no accessible name is unusable. */
    label: string
    disabled?: boolean
    className?: string
}) {
    const [interacted, setInteracted] = useState(false)
    const node = useRef<HTMLButtonElement | null>(null)

    return (
        <button
            ref={node}
            type="button"
            role="switch"
            aria-checked={checked}
            aria-label={label}
            disabled={disabled}
            data-on={checked}
            onClick={() => {
                setInteracted(true)
                onChange(!checked)
            }}
            className={cn('t-toggle dash-toggle', interacted && 'is-init', className)}
        >
            <span className="t-toggle-thumb dash-toggle-thumb" aria-hidden />
        </button>
    )
}
