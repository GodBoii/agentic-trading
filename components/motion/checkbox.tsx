'use client'

import { useEffect, useRef } from 'react'
import { cn } from '@/lib/cn'

/**
 * Recipe 25 — checkbox check.
 *
 * The box fills first, then the checkmark draws itself over the following
 * 350ms. Unchecking reverses in 150ms with no draw — the ceremony belongs to
 * the commitment, not the undo.
 *
 * The draw *transitions* `stroke-dashoffset` rather than animating it, so an
 * uncheck part-way through the draw reverses cleanly from wherever the stroke
 * got to instead of jumping to the end first.
 *
 * `--check-len` is measured from the path on mount rather than hardcoded: a
 * dasharray that does not match the path length makes the stroke either
 * pre-reveal or over-draw, and hardcoding it breaks silently the moment the
 * path is edited.
 */
export function Checkbox({
    checked,
    onChange,
    label,
    disabled,
    size = 16,
    className,
}: {
    checked: boolean
    onChange: (next: boolean) => void
    label: string
    disabled?: boolean
    size?: number
    className?: string
}) {
    const host = useRef<HTMLButtonElement | null>(null)
    const path = useRef<SVGPathElement | null>(null)

    useEffect(() => {
        const node = path.current
        const element = host.current
        if (!node || !element) return
        element.style.setProperty('--check-len', String(Math.ceil(node.getTotalLength()) + 1))
    }, [])

    return (
        <button
            ref={host}
            type="button"
            role="checkbox"
            aria-checked={checked}
            aria-label={label}
            disabled={disabled}
            onClick={() => onChange(!checked)}
            style={{ width: size, height: size }}
            className={cn(
                't-check t-press grid flex-shrink-0 place-items-center rounded-[5px] border',
                checked
                    ? 'border-accent/60 bg-accent/[0.16] text-accent'
                    : 'border-line-strong bg-surface text-transparent',
                disabled && 'cursor-not-allowed opacity-40',
                className,
            )}
        >
            <svg
                width={Math.round(size * 0.66)}
                height={Math.round(size * 0.66)}
                viewBox="0 0 12 12"
                fill="none"
                aria-hidden
            >
                <path
                    ref={path}
                    d="M2 6.2L4.7 9L10 2.6"
                    stroke="currentColor"
                    strokeWidth={1.9}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                />
            </svg>
        </button>
    )
}
