'use client'

import { Reveal, useRevealList } from '@/components/motion/reveal'
import { Tilt } from '@/components/motion/tilt'

/**
 * Platform — what the system actually does.
 *
 * The four real services in the stack, on a dense asymmetric grid.
 *
 * It was a 2x2 of identical tiles. Four equal boxes is the layout a template
 * reaches for when it has four things and no opinion about them, and it flattened
 * a pipeline — these run in sequence, and two of them carry most of the product's
 * weight — into a set of peers. The grid is now three columns where the scanner
 * and the agents each take two, so the row lengths interlock exactly (2+1, then
 * 1+2) and no cell is left empty. Column spans collapse to one below `md`, where
 * a three-column ruled grid is unreadable anyway.
 *
 * Motion. Two recipes, each with a distinct job:
 *
 *   - Texts reveal (recipe 18) for the section heading and, through
 *     `useRevealList`, for the four cards. The hook returns props to spread rather
 *     than rendering a wrapper, because inserting a `div` between the grid and its
 *     cells would break the `gap-px` hairline construction that draws the
 *     dividers.
 *
 *   - Card tilt (recipe 19) on each module. These tiles are the one place on the
 *     site whose job is to feel tangible, and the glare tracking the cursor gives
 *     the flat grid some physicality. Deliberately restricted to the landing page:
 *     tilting a panel of live P&L figures would make them harder to read. The
 *     effect turns itself off on coarse pointers, where `touch-action: none` on a
 *     full-width card would otherwise swallow the scroll gesture.
 *
 * Replaces four `framer-motion` `whileInView` articles with per-index delays of
 * `i * 0.06` over 0.7s — off-token numbers that nothing else shared.
 */

const MODULES = [
    {
        num: '01',
        name: 'Universe scanner',
        description:
            'Screens the NSE universe and builds a focused watchlist of instruments worth watching this session, so the agents never start from three thousand names.',
        span: 'md:col-span-2',
    },
    {
        num: '02',
        name: 'Market data gateway',
        description: 'Streams live quotes and depth through your broker connection.',
        span: 'md:col-span-1',
    },
    {
        num: '03',
        name: 'Signal engine',
        description: 'Evaluates indicators across the watchlist and flags setups as they form.',
        span: 'md:col-span-1',
    },
    {
        num: '04',
        name: 'Trading agents',
        description:
            'Reason over each signal, size the position inside your capital limit, and execute through Dhan. Every step is written to the run log, so a decision can be read back long after it was made.',
        span: 'md:col-span-2',
    },
]

export default function AgentNetwork() {
    const { containerProps, lineClass } = useRevealList<HTMLDivElement>({ margin: '-10%' })

    return (
        <section id="platform" className="relative border-t border-line px-5 py-24 sm:px-8 sm:py-32">
            <div className="mx-auto max-w-6xl">
                <Reveal margin="-15%" className="max-w-2xl">
                    <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-accent">The platform</p>
                    <h2 className="mt-5 font-display text-[30px] font-medium leading-[1.08] tracking-[-0.03em] sm:text-[44px]">
                        Four services, one pipeline.
                    </h2>
                    <p className="mt-5 max-w-xl text-[15px] leading-relaxed text-ink-secondary">
                        Each part does one job. Together they take a session from scan to supervised execution.
                    </p>
                </Reveal>

                <div
                    {...containerProps}
                    className={`mt-14 grid gap-px overflow-hidden rounded-2xl border border-line bg-line md:grid-cols-3 ${containerProps.className}`}
                >
                    {MODULES.map((module, index) => (
                        <article key={module.num} className={`${module.span} ${lineClass(index)}`}>
                            {/* The tilt wrapper is inside the grid cell, so the
                                cell keeps its hairline edges while the card
                                itself leans. */}
                            <Tilt
                                className="h-full"
                                cardClassName="flex h-full flex-col rounded-none bg-[var(--site-canvas-raised)] p-7 sm:p-8"
                            >
                                <span className="font-mono text-[11px] tracking-[0.18em] text-ink-tertiary">
                                    {module.num}
                                </span>
                                <h3 className="mt-4 font-display text-[19px] font-medium tracking-[-0.02em]">
                                    {module.name}
                                </h3>
                                <p className="mt-3 max-w-prose text-[13.5px] leading-relaxed text-ink-secondary">
                                    {module.description}
                                </p>
                            </Tilt>
                        </article>
                    ))}
                </div>
            </div>
        </section>
    )
}
