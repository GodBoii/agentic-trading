'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import BrandMark from '@/components/brand-mark'
import { PrimaryCta } from './cta'

/**
 * Nav — brand, section links, auth actions.
 *
 * Static bar with a backdrop blur. No scroll-linked motion and no animated
 * indicator: a header that reacts to scrolling competes with the section
 * reveals happening underneath it.
 *
 * Motion. Only two things move here, and both are responses to a real state
 * change rather than decoration:
 *
 *   - The section links draw an underline in on hover. The rule grows from the
 *     left over 250ms, so it reads as the link acknowledging the pointer.
 *
 *   - The auth actions swap label when the session resolves ("Sign in" →
 *     "Dashboard", "Get started" → "Open app"). Because that state arrives
 *     asynchronously after mount, the label would otherwise change between
 *     frames a beat after the page settles, which looks like a glitch. The
 *     primary action's `key` forces a remount so the swap is unambiguous.
 */

const LINKS = [
    { label: 'Platform', href: '#platform' },
    { label: 'How it works', href: '#how-it-works' },
]

export default function Nav() {
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
            if (unsubscribe) unsubscribe()
        }
    }, [])

    return (
        <header className="fixed inset-x-0 top-0 z-50 border-b border-white/[0.06] bg-[#030303]/85 backdrop-blur-md">
            <nav className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between px-5 sm:px-8">
                <Link
                    href="/"
                    className="group flex items-center gap-2.5"
                    aria-label="PolyCognition home"
                >
                    <BrandMark
                        className="h-7 w-7 transition-transform duration-[250ms] ease-[cubic-bezier(0.22,1,0.36,1)] group-hover:scale-105"
                        priority
                    />
                    <span className="font-grotesk text-sm font-semibold tracking-[-0.01em] text-white">
                        PolyCognition
                    </span>
                </Link>

                <div className="hidden items-center gap-8 md:flex">
                    {LINKS.map((link) => (
                        <a
                            key={link.label}
                            href={link.href}
                            className="group relative py-1 text-[13px] text-white/55 transition-colors duration-[250ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:text-white"
                        >
                            {link.label}
                            <span
                                aria-hidden
                                className="absolute bottom-0 left-0 h-px w-0 bg-white/40 transition-[width] duration-[250ms] ease-[cubic-bezier(0.22,1,0.36,1)] group-hover:w-full"
                            />
                        </a>
                    ))}
                </div>

                <div className="flex items-center gap-3 sm:gap-5">
                    <Link
                        href={signedIn ? '/dashboard' : '/login'}
                        className="hidden text-[13px] text-white/55 transition-colors duration-[250ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:text-white sm:inline"
                    >
                        {signedIn ? 'Dashboard' : 'Sign in'}
                    </Link>
                    <PrimaryCta
                        key={signedIn ? 'app' : 'signup'}
                        href={signedIn ? '/dashboard' : '/signup'}
                        className="px-4 py-2 text-[13px]"
                    >
                        {signedIn ? 'Open app' : 'Get started'}
                    </PrimaryCta>
                </div>
            </nav>
        </header>
    )
}
