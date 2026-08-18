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
                'group t-press inline-flex items-center justify-center gap-1.5 rounded-lg bg-white px-6 py-3 text-sm font-medium text-[#030303]',
                'transition-[background-color,box-shadow] duration-[250ms] ease-[cubic-bezier(0.22,1,0.36,1)]',
                'hover:bg-white/90 hover:shadow-[0_8px_36px_-12px_rgba(255,255,255,0.45)]',
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
                'group t-press inline-flex items-center justify-center gap-1.5 rounded-lg border border-white/[0.12] px-6 py-3 text-sm font-medium text-white/70',
                'transition-[color,border-color,background-color] duration-[250ms] ease-[cubic-bezier(0.22,1,0.36,1)]',
                'hover:border-white/25 hover:bg-white/[0.03] hover:text-white',
                className,
            )}
        >
            {children}
        </Link>
    )
}
