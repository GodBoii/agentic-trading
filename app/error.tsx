'use client'

import { useEffect } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Reveal } from '@/components/motion/reveal'
import { LearnMoreChevron } from '@/components/motion/learn-more'
import { Alert } from '@/components/ui/icons'

/**
 * Route-level error boundary.
 *
 * Motion. The copy uses the texts-reveal recipe so the screen arrives rather
 * than snapping in — an error page is jarring enough without it appearing in a
 * single frame.
 *
 * Deliberately no shake here. The error shake is validation feedback: it means
 * "the thing you just did was wrong, try again". A route-level crash is not the
 * user's action being rejected, and percussive motion on a page that is already
 * bad news reads as the interface panicking. The same reasoning applies to the
 * 404.
 */
export default function Error({
    error,
    reset,
}: {
    error: Error & { digest?: string }
    reset: () => void
}) {
    useEffect(() => {
        console.error(error)
    }, [error])

    return (
        <div className="relative flex min-h-screen w-full items-center justify-center overflow-hidden bg-[#050505] px-6">
            <div className="absolute inset-0 bg-grid-fine opacity-50" />
            <div className="pointer-events-none absolute -top-40 left-1/2 h-[600px] w-[600px] -translate-x-1/2 rounded-full bg-danger/[0.05] blur-[120px]" />

            <Reveal immediate className="relative z-10 w-full max-w-md text-center">
                <span className="mx-auto mb-6 grid h-10 w-10 place-items-center rounded-full border border-danger/30 bg-danger/[0.08] text-danger">
                    <Alert size={18} />
                </span>

                <h1 className="mb-4 font-display text-[44px] leading-[0.95] tracking-[-0.035em] text-white sm:text-[56px]">
                    Something broke.
                </h1>

                <p className="mx-auto mb-8 max-w-sm text-[14px] leading-relaxed text-ink-secondary">
                    We hit an unexpected condition. The error has been logged. You can try again or return to the
                    homepage.
                </p>

                {error.message ? (
                    <div className="mb-8 rounded-lg border border-danger/30 bg-danger/[0.08] px-4 py-3 text-left">
                        <p className="break-all font-mono text-[12px] text-danger">{error.message}</p>
                    </div>
                ) : (
                    <></>
                )}

                <div className="flex flex-col justify-center gap-3 sm:flex-row">
                    <Button variant="solid" onClick={reset} className="h-11 rounded-full px-5 text-[14px]">
                        Try again
                    </Button>
                    <Link
                        href="/"
                        className="group t-press inline-flex h-11 items-center justify-center gap-1.5 rounded-full border border-line bg-white/[0.02] px-5 text-[14px] font-medium text-white backdrop-blur-sm transition-[background-color,border-color] duration-[250ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:border-white/20 hover:bg-white/[0.06]"
                    >
                        Go home
                        <LearnMoreChevron size={15} />
                    </Link>
                </div>
            </Reveal>
        </div>
    )
}
