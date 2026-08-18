'use client'

import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { cn } from '@/lib/cn'
import { LearnMoreChevron } from '@/components/motion/learn-more'
import { TextSwap } from '@/components/motion/text-swap'

/**
 * Button — closed variant/size API.
 *
 * Three variants, each with a distinct job: `ghost` for secondary navigation
 * and toolbars, `subtle` for recovery actions inside a notice, `solid` for the
 * one committing action on a screen.
 *
 * Motion. Three behaviours, each earning its place:
 *
 *   - Press feedback (`.t-press`) on every button. A 3% depression on
 *     `:active` is the cheapest possible confirmation that the control
 *     received the event, and it costs no layout. Suppressed while disabled,
 *     so a dead control stays dead.
 *
 *   - `swapLabel` runs the label through the text-swap recipe (recipe 04), so
 *     "Refresh" → "Refreshing" and "Save" → "Saved" exchange in place rather
 *     than cutting. Opt-in, because it is only right where the label reflects
 *     a state the user just caused.
 *
 *   - `trailing="chevron"` fits the learn-more hover (recipe 24): the chevron
 *     opens into an arrow on hover. Replaces the literal `→` glyphs that were
 *     inlined across the landing and auth screens.
 */
export type ButtonVariant = 'ghost' | 'subtle' | 'solid'
export type ButtonSize = 'sm' | 'md'

const BASE =
    'group t-press inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-lg font-medium tracking-[-0.01em] disabled:cursor-not-allowed disabled:opacity-40'

/**
 * Enumerated rather than `transition-all`: a button also carries transform
 * (press) and, on the solid variant, a shadow — letting those ride on the same
 * declaration as colour means every hover re-tweens the press state too.
 */
const MOTION =
    'transition-[color,background-color,border-color,box-shadow] duration-[250ms] ease-[cubic-bezier(0.22,1,0.36,1)]'

const VARIANT: Record<ButtonVariant, string> = {
    ghost: 'border border-line text-ink-secondary hover:border-line-strong hover:bg-white/[0.04] hover:text-ink-primary',
    subtle: 'bg-white/[0.04] text-ink-secondary hover:bg-white/[0.08] hover:text-ink-primary',
    solid: 'bg-ink-primary text-canvas hover:bg-white hover:shadow-[0_6px_24px_-10px_rgba(255,255,255,0.35)]',
}

const SIZE: Record<ButtonSize, string> = {
    sm: 'h-7 px-2.5 text-[11px]',
    md: 'h-9 px-4 text-[12px]',
}

export function Button({
    children,
    variant = 'ghost',
    size = 'md',
    swapLabel = false,
    trailing,
    className,
    ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
    children: ReactNode
    variant?: ButtonVariant
    size?: ButtonSize
    /**
     * Animate the label when it changes. Requires `children` to be a plain
     * string — there is nothing to swap in an arbitrary node tree.
     */
    swapLabel?: boolean
    /** `chevron` appends the hover-opening arrow. */
    trailing?: 'chevron'
}) {
    return (
        <button
            type="button"
            className={cn(BASE, MOTION, VARIANT[variant], SIZE[size], className)}
            {...rest}
        >
            {swapLabel && typeof children === 'string' ? <TextSwap>{children}</TextSwap> : children}
            {trailing === 'chevron' && <LearnMoreChevron size={size === 'sm' ? 13 : 15} />}
        </button>
    )
}
