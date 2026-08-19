'use client'

import { Reveal } from '@/components/motion/reveal'
import { PrimaryCta, SecondaryCta } from './cta'

/**
 * Hero — professional, single-column intro.
 *
 * One clear headline, one honest paragraph, one or two actions depending on who
 * is reading.
 *
 * `signedIn` comes in as a prop. This file used to run its own `getSession()`
 * effect and its own `onAuthStateChange` subscription — a second copy of the
 * exact code in `nav.tsx`, so the page opened two independent listeners against
 * the same session and both painted the signed-out labels first. One server
 * read now feeds every section.
 *
 * Motion (recipe 18, texts reveal). 500ms rise, 12px travel, 3px blur, 40ms per
 * line, on the shared stagger tokens. `immediate` because this is above the
 * fold: waiting for an intersection callback on content already on screen just
 * delays it. Still a client component for that reveal, which is the only reason
 * it needs to be one.
 */
export default function Hero({ signedIn }: { signedIn: boolean }) {
    return (
        <section className="relative w-full bg-[#030303]">
            {/* Static, subtle top glow — deliberately not animated: a moving
                gradient behind the headline competes with the copy reveal. */}
            <div
                aria-hidden
                className="pointer-events-none absolute inset-x-0 top-0 h-[480px]"
                style={{
                    background:
                        'radial-gradient(ellipse 720px 420px at 50% -8%, rgba(0,229,255,0.07) 0%, transparent 70%)',
                }}
            />

            <div className="relative mx-auto flex min-h-[100svh] w-full max-w-6xl flex-col justify-center px-5 pb-20 pt-32 sm:px-8">
                <Reveal immediate>
                    <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-[#00E5FF]">
                        AI trading agents · Dhan broker integration
                    </p>

                    <h1 className="mt-6 max-w-3xl font-grotesk text-4xl font-semibold leading-[1.05] tracking-[-0.03em] text-white sm:text-6xl">
                        Autonomous trading intelligence for Indian markets.
                    </h1>

                    <p className="mt-6 max-w-xl text-base leading-relaxed text-white/55 sm:text-lg">
                        PolyCognition connects to your Dhan broker, scans the NSE universe, and surfaces intraday
                        opportunities, with reasoning you can read and risk limits you control.
                    </p>

                    <div className="mt-10 flex flex-col gap-4 sm:flex-row sm:items-center">
                        <PrimaryCta href={signedIn ? '/dashboard' : '/signup'}>
                            {signedIn ? 'Open dashboard' : 'Get started'}
                        </PrimaryCta>
                        {!signedIn && <SecondaryCta href="/login">Sign in</SecondaryCta>}
                    </div>

                    <p className="mt-16 max-w-xl text-[12px] leading-relaxed text-white/30">
                        Built for research and assisted execution. Markets carry risk, so review every decision before
                        capital is committed.
                    </p>
                </Reveal>
            </div>
        </section>
    )
}
