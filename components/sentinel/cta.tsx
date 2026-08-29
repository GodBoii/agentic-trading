'use client'

import Link from 'next/link'
import { cn } from '@/lib/cn'
import { LearnMoreChevron } from '@/components/motion/learn-more'

/**
 * The landing page's two call-to-action shapes.
 *
 * Previously the same pill markup — padding, radius, hover colour, and a
 * literal `→` glyph — was repeated in the nav, the hero and the final CTA,
 * with the transition duration drifting between them (300ms in some, 500ms in
 * others). One component, one set of tokens.
 *
 * The trailing arrow is the learn-more recipe (recipe 24) rather than a text
 * glyph: the chevron's arms open into an arrow on hover. A `→` character
 * renders at a different weight and baseline in every font on the page and
 * cannot be animated beyond a crude translate.
 */
export function PrimaryCta({
    href,
    children,
    className,
}: {
    href: string
    children: React.ReactNode
    className?: string
}) {
    return (
        <Link
            href={href}
            className={cn(
                'group t-press inline-flex items-center justify-center gap-1.5 rounded-lg bg-solid px-6 py-3 text-sm font-medium text-solid-fg',
                'transition-[background-color,box-shadow] duration-fast ease-smooth',
                'hover:bg-solid-hover hover:shadow-solid',
                className,
            )}
        >
            {children}
            <LearnMoreChevron size={16} />
        </Link>
    )
}

export function SecondaryCta({
    href,
    children,
    className,
}: {
    href: string
    children: React.ReactNode
    className?: string
}) {
    return (
        <Link
            href={href}
            className={cn(
                'group t-press inline-flex items-center justify-center gap-1.5 rounded-lg border border-line-strong px-6 py-3 text-sm font-medium text-ink-secondary',
                'transition-[color,border-color,background-color] duration-fast ease-smooth',
                'hover:border-line-strong hover:bg-surface-hover hover:text-ink-primary',
                className,
            )}
        >
            {children}
        </Link>
    )
}
