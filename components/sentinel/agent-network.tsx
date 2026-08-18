'use client'

import { Reveal, useRevealList } from '@/components/motion/reveal'
import { Tilt } from '@/components/motion/tilt'

/**
 * Platform — what the system actually does.
 *
 * A calm 2×2 grid describing the real services in the stack.
 *
 * Motion. Two recipes, each with a distinct job:
 *
 *   - Texts reveal (recipe 18) for the section heading and, via
 *     `useRevealList`, for the four cards. The hook returns props to spread
 *     rather than rendering a wrapper, because inserting a `div` between the
 *     grid and its cells would break the `gap-px` hairline construction that
 *     draws the dividers.
 *
 *   - Card tilt (recipe 19) on each module. These tiles are the one place on
 *     the site whose job is to feel tangible, and the glare tracking the cursor
 *     gives the flat grid some physicality. Deliberately restricted to the
 *     landing page: tilting a panel of live P&L figures would make them harder
 *     to read.
 *
 * Replaces four `framer-motion` `whileInView` articles with per-index delays of
 * `i * 0.06` over 0.7s — off-token numbers that nothing else shared.
 */

const MODULES = [
    {
        num: '01',
        name: 'Universe Scanner',
        description:
            'Screens the NSE universe and builds a focused watchlist of instruments worth watching each session.',
    },
    {
        num: '02',
        name: 'Market Data Gateway',
        description:
            'Streams live quotes and market depth through your broker connection so agents always work from current data.',
    },
    {
        num: '03',
        name: 'Signal Engine',
        description:
            'Evaluates technical indicators across the watchlist and flags intraday setups as they form.',
    },
    {
        num: '04',
        name: 'AI Trading Agents',
        description:
            'Reason over every signal, size positions within your risk bounds, and execute through Dhan — each step logged and explainable.',
    },
]

export default function AgentNetwork() {
    const { containerProps, lineClass } = useRevealList<HTMLDivElement>({ margin: '-10%' })

    return (
        <section
            id="platform"
            className="relative border-t border-white/[0.05] bg-[#030303] px-5 py-24 sm:px-8 sm:py-32"
        >
            <div className="mx-auto max-w-6xl">
                <Reveal margin="-15%" className="max-w-2xl">
                    <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-[#00E5FF]">The platform</p>
                    <h2 className="mt-5 font-grotesk text-3xl font-semibold tracking-[-0.03em] text-white sm:text-5xl">
                        Four services, one pipeline.
                    </h2>
                    <p className="mt-5 text-base leading-relaxed text-white/55">
                        Each part of the system does one job well. Together they take a market session from scan to
                        supervised execution.
                    </p>
                </Reveal>

                <div
                    {...containerProps}
                    className={`mt-14 grid gap-px overflow-hidden rounded-2xl border border-white/[0.06] bg-white/[0.06] sm:grid-cols-2 ${containerProps.className}`}
                >
                    {MODULES.map((module, index) => (
                        <article key={module.num} className={lineClass(index)}>
                            {/* The tilt wrapper is inside the grid cell, so the
                                cell keeps its hairline edges while the card
                                itself leans. */}
                            <Tilt className="h-full" cardClassName="h-full rounded-none bg-[#050505] p-7 sm:p-9">
                                <span className="font-mono text-[11px] tracking-[0.2em] text-white/30">
                                    {module.num}
                                </span>
                                <h3 className="mt-4 font-grotesk text-xl font-semibold tracking-[-0.02em] text-white">
                                    {module.name}
                                </h3>
                                <p className="mt-3 text-sm leading-relaxed text-white/50">{module.description}</p>
                            </Tilt>
                        </article>
                    ))}
                </div>
            </div>
        </section>
    )
}
