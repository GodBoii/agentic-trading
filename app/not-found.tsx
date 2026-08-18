'use client'

import Link from 'next/link'
import { Reveal } from '@/components/motion/reveal'
import { LearnMoreChevron } from '@/components/motion/learn-more'

/**
 * 404.
 *
 * Motion. Texts reveal, and nothing else. The oversized numeral is already the
 * loudest element on the page; giving it its own entrance on top of the stagger
 * would be two effects competing for the same moment, which the motion system
 * rules out — one primary visual idea per component.
 *
 * Now a client component so it can use the reveal. That is the only reason: the
 * page has no state and no handlers beyond the link.
 */
export default function NotFound() {
    return (
        <div className="relative flex min-h-screen w-full items-center justify-center overflow-hidden bg-[#050505] px-6">
            <div className="absolute inset-0 bg-grid-fine opacity-50" />
            <div className="pointer-events-none absolute -top-40 left-1/2 h-[800px] w-[800px] -translate-x-1/2 rounded-full bg-accent/[0.04] blur-[140px]" />

            <Reveal immediate className="relative z-10 w-full max-w-lg text-center">
                <div className="mb-6 inline-flex items-center gap-2">
                    <span className="h-px w-8 bg-accent" />
                    <span className="font-mono text-[11px] uppercase tracking-[0.22em] text-accent">
                        404 · Not found
                    </span>
                    <span className="h-px w-8 bg-accent" />
                </div>

                <h1 className="mb-2 font-display text-[120px] leading-[0.9] tracking-[-0.05em] text-white sm:text-[180px]">
                    4<span className="font-serif-italic text-white/60">0</span>4
                </h1>

                <h2 className="mb-3 font-display text-[24px] tracking-[-0.025em] text-white sm:text-[28px]">
                    Lost in the market.
                </h2>

                <p className="mx-auto mb-10 max-w-sm text-[14px] leading-relaxed text-ink-secondary">
                    The page you&apos;re looking for doesn&apos;t exist — or it has been moved to a new position.
                </p>

                <Link
                    href="/"
                    className="group t-press inline-flex items-center justify-center gap-1.5 rounded-full bg-white px-5 py-3 text-[14px] font-medium text-black transition-[background-color,box-shadow] duration-[250ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:bg-white/90 hover:shadow-[0_8px_36px_-12px_rgba(255,255,255,0.45)]"
                >
                    Return home
                    <LearnMoreChevron size={15} />
                </Link>
            </Reveal>
        </div>
    )
}
