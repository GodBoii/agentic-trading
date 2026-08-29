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
 * than snapping in — an error page is jarring enough without appearing in a
 * single frame.
 *
 * Deliberately no shake. The error shake is validation feedback: it means "the
 * thing you just did was wrong, try again". A route-level crash is not the
 * user's action being rejected, and percussive motion on a page that is already
 * bad news reads as the interface panicking. The same reasoning applies to the
 * 404.
 *
 * Left-aligned rather than centred, and 34px rather than 56px. A centred display
 * headline over a centred paragraph over two centred buttons is the generic
 * error layout, and at 56px "Something broke." was the largest type anywhere in
 * the product — shouting at someone whose request just failed.
 */
export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
    useEffect(() => {
        // The only diagnostic channel available in a client error boundary.
        console.error(error)
    }, [error])

    return (
        <div className="grain relative flex min-h-[100dvh] w-full items-center overflow-hidden bg-canvas px-5 text-ink-primary sm:px-8">
            <div aria-hidden className="pointer-events-none absolute inset-0 bg-grid-fine bg-grid-fade" />

            <Reveal immediate className="relative z-[2] mx-auto w-full max-w-xl">
                <span className="mb-5 inline-flex items-center gap-2 rounded-md border border-danger/25 bg-danger/[0.07] px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-danger">
                    <Alert size={13} />
                    Unhandled error
                </span>

                <h1 className="font-display text-[30px] leading-[1.05] tracking-[-0.035em] sm:text-[36px]">
                    This screen failed to render.
                </h1>

                <p className="mt-3 max-w-md text-[13.5px] leading-relaxed text-ink-secondary">
                    The error is logged. Retrying re-runs just this route, so anything you had open elsewhere in the app
                    is untouched.
                </p>

                {error.message ? (
                    <div className="mt-6 rounded-xl border border-line bg-panel-inset p-3.5">
                        <p className="dash-label mb-1.5">Reported</p>
                        <p className="break-all font-mono text-[11.5px] leading-relaxed text-ink-secondary">
                            {error.message}
                        </p>
                        {error.digest && (
                            <p className="mt-2 font-mono text-[10px] text-ink-tertiary">digest {error.digest}</p>
                        )}
                    </div>
                ) : (
                    <></>
                )}

                <div className="mt-7 flex flex-col gap-2.5 sm:flex-row sm:items-center">
                    <Button variant="solid" size="lg" onClick={reset}>
                        Try again
                    </Button>
                    <Link
                        href="/dashboard"
                        className="group t-press inline-flex h-11 items-center justify-center gap-1.5 rounded-lg border border-line px-5 text-[13.5px] font-medium text-ink-secondary transition-[color,background-color,border-color] duration-fast ease-smooth hover:border-line-strong hover:bg-surface-hover hover:text-ink-primary"
                    >
                        Back to portfolio
                        <LearnMoreChevron size={15} />
                    </Link>
                </div>
            </Reveal>
        </div>
    )
}
