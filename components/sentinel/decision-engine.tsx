'use client'

import { Reveal, useRevealList } from '@/components/motion/reveal'

/**
 * How it works — the pipeline, in three steps.
 *
 * Motion (recipe 18, texts reveal). The three steps stagger left to right at
 * 40ms apart, so the sequence is read in order rather than arriving as a block.
 * That ordering is the content here: these are numbered steps, and the reveal
 * reinforces the direction of the flow.
 *
 * `useRevealList` is used instead of `Reveal` so the `<li>` elements stay direct
 * children of the `<ol>` — wrapping them in `div`s would break both the grid
 * and the list semantics.
 */

const STEPS = [
    {
        num: '1',
        title: 'Connect your broker',
        description:
            'Link your Dhan account once. Authentication and token renewal are handled for you in the background.',
    },
    {
        num: '2',
        title: 'Agents scan and reason',
        description:
            'The scanner and signal engine watch the market while AI agents evaluate each opportunity and write down why it qualifies.',
    },
    {
        num: '3',
        title: 'You stay in control',
        description:
            'Review signals, positions, and full trade history from the dashboard. Risk limits bound every automated action.',
    },
]

export default function DecisionEngine() {
    const { containerProps, lineClass } = useRevealList<HTMLOListElement>({ margin: '-10%' })

    return (
        <section
            id="how-it-works"
            className="relative border-t border-white/[0.05] bg-[#030303] px-5 py-24 sm:px-8 sm:py-32"
        >
            <div className="mx-auto max-w-6xl">
                <Reveal margin="-15%" className="max-w-2xl">
                    <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-[#00E5FF]">How it works</p>
                    <h2 className="mt-5 font-grotesk text-3xl font-semibold tracking-[-0.03em] text-white sm:text-5xl">
                        From connection to execution in three steps.
                    </h2>
                </Reveal>

                <ol
                    {...containerProps}
                    className={`mt-14 grid gap-10 sm:grid-cols-3 sm:gap-8 ${containerProps.className}`}
                >
                    {STEPS.map((step, index) => (
                        <li
                            key={step.num}
                            className={`group relative border-t border-white/[0.08] pt-6 ${lineClass(index)}`}
                        >
                            {/* The rule above each step draws itself in as the
                                step arrives, so the row reads as a progression
                                rather than three finished columns. */}
                            <span
                                aria-hidden
                                className="absolute -top-px left-0 h-px w-0 bg-[#00E5FF]/60 transition-[width] duration-[500ms] ease-[cubic-bezier(0.22,1,0.36,1)] group-hover:w-full"
                            />
                            <span className="font-grotesk text-sm font-semibold text-[#00E5FF]">{step.num}</span>
                            <h3 className="mt-3 font-grotesk text-lg font-semibold tracking-[-0.02em] text-white">
                                {step.title}
                            </h3>
                            <p className="mt-3 text-sm leading-relaxed text-white/50">{step.description}</p>
                        </li>
                    ))}
                </ol>
            </div>
        </section>
    )
}
