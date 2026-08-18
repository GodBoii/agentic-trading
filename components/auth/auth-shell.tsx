'use client'

import Link from 'next/link'
import type { ReactNode } from 'react'
import BrandMark from '@/components/brand-mark'
import { LearnMoreChevron } from '@/components/motion/learn-more'
import { Reveal } from '@/components/motion/reveal'

/**
 * Shared chrome for the sign-in and sign-up screens.
 *
 * The two pages previously duplicated the entire frame — ambient background,
 * brand header, back link, eyebrow, headline, card, footer link — along with
 * eleven separate `framer-motion` wrappers whose delays (0.1, 0.15, 0.2, 0.25,
 * 0.5) were transcribed by hand in both files.
 *
 * Motion (recipe 18, texts reveal). The whole block above the card is one
 * staggered reveal at 40ms per line, and the card itself follows as the last
 * line. The entrance now completes in roughly 620ms rather than the previous
 * 1.3s, and it uses the same rhythm as every other heading in the product.
 *
 * `immediate`, because an auth screen is entirely above the fold — waiting on
 * an intersection callback here would only add latency.
 */
export function AuthShell({
    eyebrow,
    title,
    subtitle,
    children,
    footer,
}: {
    /** The small marker above the headline. Carries its own tone. */
    eyebrow: ReactNode
    title: ReactNode
    subtitle: string
    /** The form card. */
    children: ReactNode
    footer: ReactNode
}) {
    return (
        <div className="relative min-h-screen w-full overflow-hidden bg-[#050505]">
            {/* Static ambience. Deliberately unanimated: a drifting gradient
                behind a form competes with the field focus states, which are
                the only motion that matters on this screen. */}
            <div className="absolute inset-0 bg-grid-fine opacity-50" />
            <div className="absolute inset-0 bg-spotlight" />
            <div className="pointer-events-none absolute -left-40 -top-40 h-[500px] w-[500px] rounded-full bg-accent/[0.06] blur-[120px]" />
            <div className="pointer-events-none absolute -bottom-40 -right-40 h-[500px] w-[500px] rounded-full bg-success/[0.04] blur-[120px]" />

            <header className="relative z-10 mx-auto flex max-w-7xl items-center justify-between px-6 py-6 lg:px-8">
                <Link href="/" className="group flex items-center gap-2.5">
                    <BrandMark
                        className="h-8 w-8 transition-transform duration-[250ms] ease-[cubic-bezier(0.22,1,0.36,1)] group-hover:scale-105"
                        priority
                    />
                    <span className="text-[15px] font-medium tracking-[-0.02em] text-white">PolyCognition</span>
                </Link>
                <Link
                    href="/"
                    className="group inline-flex items-center gap-1.5 text-[12px] tracking-[-0.01em] text-white/50 transition-colors duration-[250ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:text-white"
                >
                    {/* Mirrored so the chevron opens backwards, toward home. */}
                    <span className="rotate-180">
                        <LearnMoreChevron size={13} />
                    </span>
                    Back to home
                </Link>
            </header>

            <main className="relative z-10 flex items-center justify-center px-6 py-12 sm:py-20">
                <Reveal immediate className="w-full max-w-md">
                    <div className="mb-6 inline-flex items-center gap-2">{eyebrow}</div>

                    <h1 className="mb-3 font-display text-[44px] leading-[0.95] tracking-[-0.035em] text-white sm:text-[52px]">
                        {title}
                    </h1>

                    <p className="mb-10 text-[14px] text-ink-secondary">{subtitle}</p>

                    <div className="surface rounded-2xl p-7 sm:p-8">{children}</div>

                    <p className="mt-8 text-center text-[13px] text-ink-secondary">{footer}</p>
                </Reveal>
            </main>
        </div>
    )
}

/** Divider between the credential form and the federated option. */
export function AuthDivider() {
    return (
        <div className="relative my-6">
            <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-line" />
            </div>
            <div className="relative flex justify-center">
                <span className="bg-[#0E0E10] px-3 font-mono text-[10px] uppercase tracking-[0.22em] text-ink-tertiary">
                    or
                </span>
            </div>
        </div>
    )
}
