import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { cn } from '@/lib/cn'

/**
 * Button — closed variant/size API.
 *
 * Replaces the `dash-btn !px-3 !py-1.5 !text-[11px]` pattern that was used as a
 * stand-in for size variants; overriding a component's padding with
 * `!important` from the call site is how button sizing drifts per screen.
 *
 * Three variants, each with a distinct job: `ghost` for secondary navigation
 * and toolbars, `subtle` for recovery actions inside a notice, `solid` for the
 * one committing action on a screen.
 */
export type ButtonVariant = 'ghost' | 'subtle' | 'solid'
export type ButtonSize = 'sm' | 'md'

const BASE =
    'inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-lg font-medium tracking-[-0.01em] transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-40'

const VARIANT: Record<ButtonVariant, string> = {
    ghost: 'border border-line text-ink-secondary hover:border-line-strong hover:bg-white/[0.03] hover:text-ink-primary',
    subtle: 'bg-white/[0.04] text-ink-secondary hover:bg-white/[0.07] hover:text-ink-primary',
    solid: 'bg-ink-primary text-canvas hover:bg-white',
}

const SIZE: Record<ButtonSize, string> = {
    sm: 'h-7 px-2.5 text-[11px]',
    md: 'h-9 px-4 text-[12px]',
}

export function Button({
    children,
    variant = 'ghost',
    size = 'md',
    className,
    ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
    children: ReactNode
    variant?: ButtonVariant
    size?: ButtonSize
}) {
    return (
        <button
            type="button"
            className={cn(BASE, VARIANT[variant], SIZE[size], className)}
            {...rest}
        >
            {children}
        </button>
    )
}
