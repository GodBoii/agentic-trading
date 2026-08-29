'use client'

import { BorderBeam } from '@/components/motion/border-beam'
import { Reveal } from '@/components/motion/reveal'
import { PrimaryCta, SecondaryCta } from './cta'

/**
 * Final CTA — quiet closing section.
 *
 * The copy and the actions both depend on the session, because the signed-out
 * version of this section is a pitch and the signed-in version is a door.
 *
 * This is where the page was most obviously broken. "Get started" and "Sign in"
 * were hard-coded, so someone already signed in scrolled to the bottom of the
 * page and was asked to create an account and then log in, under a line of copy
 * telling them to create an account and connect Dhan — three instructions they
 * had already followed. The section did not read the session at all, unlike the
 * nav and hero, which each read it separately.
 *
 * Motion. The copy uses texts reveal (recipe 18). The primary action carries a
 * breathing border beam, the single most emphasised control on the site and the
 * only animated edge on the page.
 *
 * `pulse` rather than the traveling beam: a glow orbiting a button reads as a
 * loading state, which is the wrong signal on an action nobody has pressed yet.
 * Breathing reads as "this is the thing to press". Strength is held at 0.55 so
 * it registers peripherally without becoming the loudest element in view.
 */
export default function FinalCta({ signedIn }: { signedIn: boolean }) {
    return (
        <section className="relative border-t border-line px-5 py-24 sm:px-8 sm:py-32">
            <div className="mx-auto max-w-6xl">
                <Reveal margin="-15%">
                    <h2 className="max-w-3xl font-display text-[30px] font-medium leading-[1.08] tracking-[-0.03em] sm:text-[44px]">
                        Put agents to work on your watchlist.
                    </h2>
                    <p className="mt-5 max-w-xl text-[15px] leading-relaxed text-ink-secondary">
                        {signedIn
                            ? 'Your workspace is ready. Open the dashboard to check balances, review what the agents found, and decide what trades.'
                            : 'Create an account, connect Dhan, and let the system show you what it finds. You decide what trades.'}
                    </p>
                    <div className="mt-10 flex flex-col gap-4 sm:flex-row sm:items-center">
                        {/* `self-start` matters on a phone. In the stacked
                            column the wrapper stretches to the full row width
                            while the button inside stays shrink-wrapped, so the
                            beam drew a wide empty frame reaching off to the right
                            of the control it was meant to outline. */}
                        <BorderBeam
                            mode="pulse"
                            tone="accent"
                            strength={0.55}
                            className="inline-flex self-start rounded-lg"
                        >
                            <PrimaryCta href={signedIn ? '/dashboard' : '/signup'}>
                                {signedIn ? 'Open dashboard' : 'Get started'}
                            </PrimaryCta>
                        </BorderBeam>
                        {!signedIn && <SecondaryCta href="/login">Sign in</SecondaryCta>}
                    </div>
                </Reveal>
            </div>
        </section>
    )
}
