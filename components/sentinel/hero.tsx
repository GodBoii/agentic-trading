'use client'

import { Reveal } from '@/components/motion/reveal'
import { PrimaryCta, SecondaryCta } from './cta'

/**
 * Hero — one headline, one honest paragraph, one or two actions depending on who
 * is reading.
 *
 * `signedIn` comes in as a prop. This file used to run its own `getSession()`
 * effect and its own `onAuthStateChange` subscription — a second copy of the code
 * in `nav.tsx`, so the page opened two independent listeners against the same
 * session and both painted the signed-out labels first. One server read now feeds
 * every section.
 *
 * The headline sizes with `clamp` in a wide container rather than jumping between
 * two fixed sizes. That is the fix for the failure mode where a display heading
 * wraps to five or six lines at an intermediate width: the container stays wide
 * enough for the words to flow, and the size gives way instead of the line count.
 *
 * The three figures under the copy are the only numbers on the page and they are
 * structural facts about the system, not performance claims. Invented returns
 * would be the worst possible thing to put on a trading product's front page.
 *
 * Motion (recipe 18, texts reveal). 500ms rise, 12px travel, 3px blur, 40ms per
 * line, on the shared stagger tokens. `immediate` because this is above the fold:
 * waiting for an intersection callback on content already on screen just delays
 * it. Still a client component for that reveal, which is the only reason it needs
 * to be one.
 */

const FACTS = [
    { value: 'NSE', label: 'Equity universe scanned each session' },
    { value: 'Dhan', label: 'Broker connection for data and execution' },
    { value: 'Full log', label: 'Every agent decision kept and replayable' },
]

export default function Hero({ signedIn }: { signedIn: boolean }) {
    return (
        <section className="relative w-full">
            {/* Static, subtle top glow. Deliberately not animated: a moving
                gradient behind the headline competes with the copy reveal. */}
            <div aria-hidden className="pointer-events-none absolute inset-x-0 top-0 h-[520px] bg-spotlight" />
            <div
                aria-hidden
                className="pointer-events-none absolute inset-x-0 top-0 h-[520px] bg-grid bg-grid-fade opacity-60"
            />

            {/*
             * `my-auto` on the child rather than `justify-center` on the parent.
             * They centre identically when the content fits, but when it does not
             * — a phone, where the copy, actions, three facts and the disclaimer
             * together exceed the viewport — `justify-content: center` pushes the
             * top of the content out through the container's top edge, and the
             * headline ends up underneath the fixed nav. Auto margins clamp at
             * zero instead, so the overflow only ever grows downward.
             */}
            <div className="relative mx-auto flex min-h-[100dvh] w-full max-w-6xl flex-col px-5 pb-20 pt-28 sm:px-8 sm:pt-32">
                <Reveal immediate className="my-auto">
                    <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-accent">
                        AI trading agents for Indian markets
                    </p>

                    <h1
                        className="mt-6 max-w-[52rem] font-display font-medium leading-[1.02] tracking-[-0.035em]"
                        style={{ fontSize: 'clamp(2.5rem, 1.4rem + 4.4vw, 4.75rem)' }}
                    >
                        Read the reasoning before the money moves.
                    </h1>

                    <p className="mt-6 max-w-xl text-[15px] leading-relaxed text-ink-secondary sm:text-[17px]">
                        PolyCognition connects to your Dhan broker, scans the NSE universe, and surfaces intraday
                        setups. Every agent writes down what it saw and why, and nothing executes outside the capital
                        limit you set.
                    </p>

                    <div className="mt-9 flex flex-col gap-3 sm:flex-row sm:items-center">
                        <PrimaryCta href={signedIn ? '/dashboard' : '/signup'}>
                            {signedIn ? 'Open dashboard' : 'Get started'}
                        </PrimaryCta>
                        {!signedIn && <SecondaryCta href="/login">Sign in</SecondaryCta>}
                    </div>

                    <dl className="mt-16 grid max-w-3xl gap-x-8 gap-y-6 border-t border-line pt-7 sm:grid-cols-3">
                        {FACTS.map((fact) => (
                            <div key={fact.value}>
                                <dt className="font-display text-[19px] font-medium tracking-[-0.02em]">
                                    {fact.value}
                                </dt>
                                <dd className="mt-1.5 text-[12px] leading-relaxed text-ink-tertiary">{fact.label}</dd>
                            </div>
                        ))}
                    </dl>

                    <p className="mt-10 max-w-xl text-[12px] leading-relaxed text-ink-tertiary">
                        Built for research and assisted execution. Markets carry risk, so review every decision before
                        capital is committed.
                    </p>
                </Reveal>
            </div>
        </section>
    )
}
