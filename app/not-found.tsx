'use client'

import Link from 'next/link'
import { Reveal } from '@/components/motion/reveal'
import { LearnMoreChevron } from '@/components/motion/learn-more'

/**
 * 404.
 *
 * Motion. Texts reveal, and nothing else. One primary visual idea per component:
 * giving the numeral its own entrance on top of the stagger would be two effects
 * competing for the same moment.
 *
 * The 180px numeral is gone. A house-sized "404" is decoration standing in for
 * an answer, and it pushed the only useful thing on the page — a way out — below
 * the fold on a phone. What replaced it is the three routes that exist, so a
 * mistyped URL lands on a directory rather than on a dead end with one button.
 *
 * A client component only for the reveal; there is no state and no handler
 * beyond the links.
 */

const ROUTES = [
    { href: '/dashboard', label: 'Portfolio', detail: 'Balances, positions and order flow' },
    { href: '/dashboard/ai-trading', label: 'Agent', detail: 'The live run and its capital limit' },
    { href: '/dashboard/trades', label: 'Trades', detail: 'Archived runs by trading day' },
]

export default function NotFound() {
    return (
        <div className="grain relative flex min-h-[100dvh] w-full items-center overflow-hidden bg-canvas px-5 text-ink-primary sm:px-8">
            <div aria-hidden className="pointer-events-none absolute inset-0 bg-grid-fine bg-grid-fade" />

            <Reveal immediate className="relative z-[2] mx-auto w-full max-w-xl">
                <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-ink-tertiary">Error 404</p>

                <h1 className="mt-4 font-display text-[30px] leading-[1.05] tracking-[-0.035em] sm:text-[36px]">
                    There is no page at this address.
                </h1>

                <p className="mt-3 max-w-md text-[13.5px] leading-relaxed text-ink-secondary">
                    The link may be out of date. Everything the app does lives behind one of these three.
                </p>

                <nav aria-label="Sections" className="mt-7 overflow-hidden rounded-2xl border border-line bg-panel shadow-panel">
                    {ROUTES.map((route) => (
                        <Link
                            key={route.href}
                            href={route.href}
                            className="group flex items-center justify-between gap-4 border-b border-line px-4 py-3.5 transition-colors duration-fast ease-smooth last:border-b-0 hover:bg-surface-hover"
                        >
                            <span className="min-w-0">
                                <span className="block text-[13px] font-medium text-ink-primary">{route.label}</span>
                                <span className="mt-0.5 block text-[11px] text-ink-tertiary">{route.detail}</span>
                            </span>
                            <span className="flex-shrink-0 text-ink-tertiary transition-colors duration-fast group-hover:text-ink-primary">
                                <LearnMoreChevron size={15} />
                            </span>
                        </Link>
                    ))}
                </nav>

                <Link
                    href="/"
                    className="group mt-6 inline-flex items-center gap-1.5 text-[12.5px] text-ink-secondary transition-colors duration-fast ease-smooth hover:text-ink-primary"
                >
                    Or go back to the homepage
                    <LearnMoreChevron size={14} />
                </Link>
            </Reveal>
        </div>
    )
}
