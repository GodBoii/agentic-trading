'use client'

import type { InputHTMLAttributes } from 'react'
import { cn } from '@/lib/cn'
import { IconSwap } from '@/components/motion/icon-swap'
import { LearnMoreChevron } from '@/components/motion/learn-more'
import { Spinner } from '@/components/ui/spinner'
import { TextSwap } from '@/components/motion/text-swap'

/**
 * Labelled credential input.
 *
 * The border tone and the shake both live on the input itself here (unlike the
 * trade-sizing field, which wraps its input to leave room for a currency
 * glyph), so `.t-input` goes directly on the element that owns the border.
 */
export function AuthField({
    id,
    label,
    className,
    ...rest
}: InputHTMLAttributes<HTMLInputElement> & { id: string; label: string }) {
    return (
        <div>
            <label
                htmlFor={id}
                className="mb-2 block font-mono text-[11px] uppercase tracking-[0.18em] text-ink-tertiary"
            >
                {label}
            </label>
            <input
                id={id}
                className={cn(
                    'w-full rounded-lg border border-line bg-[#0a0a0c] px-4 py-3 text-[14px] text-white outline-none placeholder:text-ink-tertiary',
                    'transition-[border-color,background-color,box-shadow] duration-[150ms] ease-out',
                    'focus:border-accent/50 focus:bg-[#0c0c0e] focus:shadow-[0_0_0_3px_rgb(var(--accent-rgb)/0.08)]',
                    className,
                )}
                {...rest}
            />
        </div>
    )
}

/**
 * The committing action on an auth screen.
 *
 * Motion. Two recipes replace what was previously a conditional branch swapping
 * the entire button contents between a hand-rolled `animate-spin` SVG and a
 * text-plus-arrow pair:
 *
 *   - The label swaps in place (recipe 04): "Sign in" → "Signing in".
 *   - The trailing glyph cross-fades between the chevron and a spinner
 *     (recipe 09) instead of the two swapping between frames. Because both stay
 *     mounted in one grid cell, the button's width no longer jumps when the
 *     request starts — the previous version changed its label *and* its icon at
 *     once, so the button visibly resized mid-click.
 */
export function AuthSubmit({
    pending,
    pendingLabel,
    children,
}: {
    pending: boolean
    pendingLabel: string
    children: string
}) {
    return (
        <button
            type="submit"
            disabled={pending}
            className={cn(
                'group t-press mt-2 inline-flex items-center justify-center gap-2 rounded-full bg-white px-5 py-3.5 text-[14px] font-medium text-black',
                'transition-[background-color,box-shadow,opacity] duration-[250ms] ease-[cubic-bezier(0.22,1,0.36,1)]',
                'hover:shadow-[0_0_32px_rgba(255,255,255,0.18)]',
                'disabled:cursor-not-allowed disabled:opacity-50',
            )}
        >
            <TextSwap>{pending ? pendingLabel : children}</TextSwap>
            <IconSwap
                showB={pending}
                a={<LearnMoreChevron size={15} />}
                b={<Spinner size={13} className="!border-black/25 !border-t-black" />}
            />
        </button>
    )
}

/** Federated sign-in. The mark is Google's, so its colours are literal. */
export function GoogleButton({
    onClick,
    disabled,
    label,
}: {
    onClick: () => void
    disabled?: boolean
    label: string
}) {
    return (
        <button
            type="button"
            onClick={onClick}
            disabled={disabled}
            className={cn(
                't-press inline-flex w-full items-center justify-center gap-2.5 rounded-full border border-line bg-white/[0.02] px-5 py-3 text-[14px] font-medium text-white backdrop-blur-sm',
                'transition-[background-color,border-color,opacity] duration-[250ms] ease-[cubic-bezier(0.22,1,0.36,1)]',
                'hover:border-white/20 hover:bg-white/[0.06] disabled:opacity-50',
            )}
        >
            <svg className="h-4 w-4" viewBox="0 0 24 24" aria-hidden>
                <path
                    fill="#4285F4"
                    d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                />
                <path
                    fill="#34A853"
                    d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                />
                <path
                    fill="#FBBC05"
                    d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                />
                <path
                    fill="#EA4335"
                    d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                />
            </svg>
            {label}
        </button>
    )
}
