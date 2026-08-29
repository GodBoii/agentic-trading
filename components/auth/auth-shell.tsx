'use client'

import Link from 'next/link'
import type { ReactNode } from 'react'
import BrandMark from '@/components/brand-mark'
import { LearnMoreChevron } from '@/components/motion/learn-more'
import { Reveal } from '@/components/motion/reveal'

/**
 * Shared chrome for the sign-in and sign-up screens.
 *
 * The two pages previously duplicated the whole frame — ambient background,
 * brand header, back link, eyebrow, headline, card, footer link — along with
 * eleven separate `framer-motion` wrappers whose delays (0.1, 0.15, 0.2, 0.25,
 * 0.5) were transcribed by hand in both files.
 *
 * Two things changed in the composition itself.
 *
 * The blurred colour blobs are gone. Two 500px radial smudges bleeding off
 * opposite corners is the single most recognisable generated-page decoration
 * there is, and they were doing no work: nothing on this screen needs
 * atmosphere, and the accent they carried competed with the field focus ring,
 * which is the only signal here that matters.
 *
 * The headline came down from 52px to 34px. A display size that large inside a
 * 28rem column wraps two words per line and reads as a poster rather than as a
 * page title, which is the "overlarge heading in a narrow column" failure. What
 * is left is a ruled ground that fades out, a trace of grain, and the form.
 *
 * Motion (recipe 18, texts reveal). The whole block above the card is one
 * staggered reveal at 40ms per line, and the card follows as the last line. The
 * entrance completes in roughly 620ms rather than the previous 1.3s, and it uses
 * the same rhythm as every other heading in the product. `immediate`, because an
 * auth screen is entirely above the fold; waiting on an intersection callback
 * here would only add latency.
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
        <div className="grain relative flex min-h-[100dvh] w-full flex-col overflow-hidden bg-canvas text-ink-primary">
            {/* Static ambience, deliberately unanimated: a drifting gradient
                behind a form competes with the field focus states. */}
            <div aria-hidden className="pointer-events-none absolute inset-0 bg-grid-fine bg-grid-fade" />

            <header className="relative z-[2] mx-auto flex w-full max-w-6xl items-center justify-between px-5 py-5 sm:px-8">
                <Link href="/" className="group t-press flex items-center gap-2.5">
                    <BrandMark
                        className="h-7 w-7 transition-transform duration-fast ease-smooth group-hover:scale-105"
                        priority
                    />
                    <span className="text-[14px] font-medium tracking-[-0.02em]">PolyCognition</span>
                </Link>
                <Link
                    href="/"
                    className="group inline-flex items-center gap-1.5 text-[12px] tracking-[-0.01em] text-ink-secondary transition-colors duration-fast ease-smooth hover:text-ink-primary"
                >
                    {/* Mirrored so the chevron opens backwards, toward home. */}
                    <span className="rotate-180">
                        <LearnMoreChevron size={13} />
                    </span>
                    Back to home
                </Link>
            </header>

            <main className="relative z-[2] flex flex-1 items-center px-5 py-10 sm:px-8 sm:py-16">
                <Reveal immediate className="mx-auto w-full max-w-[26rem]">
                    <div className="mb-5 inline-flex items-center gap-2">{eyebrow}</div>

                    <h1 className="font-display text-[30px] leading-[1.05] tracking-[-0.035em] text-ink-primary sm:text-[34px]">
                        {title}
                    </h1>

                    <p className="mt-3 text-[13.5px] leading-relaxed text-ink-secondary">{subtitle}</p>

                    <div className="mt-8 rounded-2xl border border-line bg-panel p-6 shadow-panel sm:p-7">
                        {children}
                    </div>

                    <p className="mt-6 text-[13px] text-ink-secondary">{footer}</p>
                </Reveal>
            </main>
        </div>
    )
}

/** Divider between the credential form and the federated option. */
export function AuthDivider() {
    return (
        <div className="relative my-6">
            <div className="absolute inset-0 flex items-center" aria-hidden>
                <div className="w-full border-t border-line" />
            </div>
            <div className="relative flex justify-center">
                {/* Matches the card, not the canvas: the label sits on the panel
                    it interrupts, so a mismatched swatch here reads as a hole. */}
                <span className="bg-panel px-3 font-mono text-[10px] uppercase tracking-[0.22em] text-ink-tertiary">
                    or
                </span>
            </div>
        </div>
    )
}
