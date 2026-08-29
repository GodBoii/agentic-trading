'use client'

import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { cn } from '@/lib/cn'
import { LearnMoreChevron } from '@/components/motion/learn-more'
import { TextSwap } from '@/components/motion/text-swap'

/**
 * Button — closed variant/size API.
 *
 * Five variants, each with one job. `ghost` for secondary navigation and
 * toolbars, `subtle` for a recovery action inside a notice, `solid` for the one
 * committing action on a screen, and `danger`/`positive` for actions whose
 * consequence is the point.
 *
 * The two tonal variants exist so call sites stop reaching for
 * `className="!bg-negative !text-[#180606]"`. Overriding a variant with
 * `!important` from outside is how a destructive button ends up a different red
 * on every screen, and it also hardcodes a foreground colour that is wrong in
 * the other theme.
 *
 * Every colour resolves to a theme token, so all five follow the light theme
 * without a second definition.
 *
 * Motion. Three behaviours, each earning its place:
 *
 *   - Press feedback (`.t-press`) on every button. A 3% depression on `:active`
 *     is the cheapest possible confirmation that the control received the event,
 *     and it costs no layout. Suppressed while disabled, so a dead control stays
 *     dead.
 *
 *   - `swapLabel` runs the label through the text-swap recipe (recipe 04), so
 *     "Refresh" to "Refreshing" and "Save" to "Saved" exchange in place rather
 *     than cutting. Opt-in, because it is only right where the label reflects a
 *     state the user just caused.
 *
 *   - `trailing="chevron"` fits the learn-more hover (recipe 24): the chevron
 *     opens into an arrow on hover. Replaces the literal arrow glyphs that were
 *     inlined across the landing and auth screens.
 */
export type ButtonVariant = 'ghost' | 'subtle' | 'solid' | 'danger' | 'positive'
export type ButtonSize = 'sm' | 'md' | 'lg'

const BASE =
    'group t-press t-tap relative inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-lg font-medium tracking-[-0.01em] disabled:cursor-not-allowed disabled:opacity-40'

/**
 * Enumerated rather than `transition-all`: a button also carries a transform
 * (press) and, on the filled variants, a shadow. Letting those ride on the same
 * declaration as colour means every hover re-tweens the press state too.
 */
const MOTION =
    'transition-[color,background-color,border-color,box-shadow] duration-fast ease-smooth'

const VARIANT: Record<ButtonVariant, string> = {
    ghost: 'border border-line text-ink-secondary hover:border-line-strong hover:bg-surface-hover hover:text-ink-primary',
    subtle: 'bg-surface-soft text-ink-secondary hover:bg-surface-strong hover:text-ink-primary',
    solid: 'bg-solid text-solid-fg hover:bg-solid-hover hover:shadow-solid',
    danger: 'bg-danger text-canvas hover:bg-danger/90',
    positive: 'bg-positive text-canvas hover:bg-positive/90',
}

const SIZE: Record<ButtonSize, string> = {
    sm: 'h-7 px-2.5 text-[11px]',
    md: 'h-9 px-4 text-[12px]',
    lg: 'h-11 px-5 text-[13.5px]',
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
        <button type="button" className={cn(BASE, MOTION, VARIANT[variant], SIZE[size], className)} {...rest}>
            {swapLabel && typeof children === 'string' ? <TextSwap>{children}</TextSwap> : children}
            {trailing === 'chevron' && <LearnMoreChevron size={size === 'sm' ? 13 : 15} />}
        </button>
    )
}
