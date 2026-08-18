'use client'

import { BorderBeam } from '@/components/motion/border-beam'
import { Reveal } from '@/components/motion/reveal'
import { PrimaryCta, SecondaryCta } from './cta'

/**
 * Final CTA — quiet closing section.
 *
 * One heading, one line, two buttons.
 *
 * Motion. The copy uses texts reveal (recipe 18). The primary action carries a
 * breathing border beam — the single most emphasised control on the site, and
 * the only place on the page an animated edge is used.
 *
 * `pulse` rather than the traveling beam: a glow orbiting a button reads as a
 * loading state, which is exactly the wrong signal on an action that has not
 * been pressed yet. Breathing reads as "this is the thing to press". Strength
 * is held at 0.55 so it registers peripherally without turning the button into
 * the loudest element in the viewport.
 */
export default function FinalCta() {
    return (
        <section className="relative border-t border-white/[0.05] bg-[#030303] px-5 py-24 sm:px-8 sm:py-32">
            <div className="mx-auto max-w-6xl">
                <Reveal margin="-15%">
                    <h2 className="max-w-2xl font-grotesk text-3xl font-semibold tracking-[-0.03em] text-white sm:text-5xl">
                        Put agents to work on your watchlist.
                    </h2>
                    <p className="mt-5 max-w-xl text-base leading-relaxed text-white/55">
                        Create an account, connect Dhan, and let the system show you what it finds — you decide what
                        trades.
                    </p>
                    <div className="mt-10 flex flex-col gap-4 sm:flex-row sm:items-center">
                        <BorderBeam mode="pulse" tone="accent" strength={0.55} className="inline-flex rounded-lg">
                            <PrimaryCta href="/signup">Get started</PrimaryCta>
                        </BorderBeam>
                        <SecondaryCta href="/login">Sign in</SecondaryCta>
                    </div>
                </Reveal>
            </div>
        </section>
    )
}
