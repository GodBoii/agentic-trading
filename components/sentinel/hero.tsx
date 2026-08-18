'use client'

import { useEffect, useState } from 'react'
import { Reveal } from '@/components/motion/reveal'
import { PrimaryCta, SecondaryCta } from './cta'

/**
 * Hero — professional, single-column intro.
 *
 * One clear headline, one honest paragraph, two actions.
 *
 * Motion (recipe 18, texts reveal). This previously used a local
 * `framer-motion` `FadeUp` wrapper with five hand-picked delays (0, 0.1, 0.2,
 * 0.3, 0.45) over an 0.8s duration — numbers that existed nowhere else in the
 * project and did not match the four other files doing the same thing. It now
 * runs on the shared stagger tokens: 500ms rise, 12px travel, 3px blur, 40ms
 * per line. The whole entrance completes in well under half a second instead
 * of the previous 1.25s, and it is the same rhythm every other heading on the
 * site uses.
 *
 * `immediate` because this is above the fold: waiting for an intersection
 * callback on content that is already on screen just delays it.
 */
export default function Hero() {
    const [signedIn, setSignedIn] = useState(false)

    useEffect(() => {
        let cancelled = false
        let unsubscribe: (() => void) | undefined

        ;(async () => {
            try {
                const mod = await import('@/lib/supabase/client').catch(() => null)
                if (!mod) return
                const supabase = mod.createClient()
                const { data } = await supabase.auth.getSession()
                if (!cancelled) setSignedIn(Boolean(data.session))
                const sub = supabase.auth.onAuthStateChange((_event, session) => {
                    if (!cancelled) setSignedIn(Boolean(session))
                })
                unsubscribe = () => sub.data.subscription.unsubscribe()
            } catch {
                /* no-op */
            }
        })()

        return () => {
            cancelled = true
            // The previous version returned this unsubscribe from inside the
            // async IIFE, where React never saw it — the auth listener leaked
            // on every unmount.
            if (unsubscribe) unsubscribe()
        }
    }, [])

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
                        opportunities — with reasoning you can read and risk limits you control.
                    </p>

                    <div className="mt-10 flex flex-col gap-4 sm:flex-row sm:items-center">
                        <PrimaryCta href={signedIn ? '/dashboard' : '/signup'}>
                            {signedIn ? 'Open dashboard' : 'Get started'}
                        </PrimaryCta>
                        {!signedIn && <SecondaryCta href="/login">Sign in</SecondaryCta>}
                    </div>

                    <p className="mt-16 max-w-xl text-[12px] leading-relaxed text-white/30">
                        Built for research and assisted execution. Markets carry risk — review every decision before
                        capital is committed.
                    </p>
                </Reveal>
            </div>
        </section>
    )
}
