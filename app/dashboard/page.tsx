'use client'

import { Suspense, useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import DhanConnect from '@/components/dhan-connect'
import PortfolioOverview from '@/components/dashboard/portfolio-overview'
import { Skeleton } from '@/components/ui/skeleton'
import { CellGrid, Panel } from '@/components/ui/panel'
import { Reveal } from '@/components/motion/reveal'
import { Toast, useToast } from '@/components/motion/toast'
import { formatHeaderDate } from '@/lib/format'

export const dynamic = 'force-dynamic'

/** Broker OAuth failure codes, mapped to something a user can act on. */
const CONNECT_ERRORS: Record<string, string> = {
    missing_token: 'Dhan did not return an authentication token. Try connecting again.',
    unauthorized: 'Please sign in before connecting Dhan.',
    server_config: 'The Dhan connection is not configured on the server.',
    token_exchange_failed: 'Dhan could not complete the token exchange.',
    invalid_response: 'Dhan returned an invalid response.',
    db_save_failed: 'The connection could not be saved. Try again.',
    unexpected: 'An unexpected connection error occurred.',
}

function DashboardContent() {
    const router = useRouter()
    const searchParams = useSearchParams()
    /**
     * The OAuth result surfaces as a toast (recipe 22): it rises on the slower
     * open clock and leaves on the faster close clock, so it reads as
     * deliberate arriving and out-of-the-way leaving. Previously an
     * `AnimatePresence` block whose exit ran at the same speed as its
     * entrance, which made dismissal feel sluggish.
     */
    const { toast, show, dismiss } = useToast()

    // Surface the result of the Dhan OAuth round trip, then clean the URL so a
    // refresh does not replay the message.
    useEffect(() => {
        const success = searchParams.get('success')
        const error = searchParams.get('error')
        if (!success && !error) return

        show(
            success === 'true'
                ? { tone: 'success', message: 'Dhan account connected.' }
                : { tone: 'error', message: CONNECT_ERRORS[error || ''] || 'Unable to connect Dhan.' },
        )
        router.replace('/dashboard')
        // `show` is stable for the life of the hook; depending on it would
        // re-fire the toast on every render.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [router, searchParams])

    /**
     * Resolved after mount. The page is server-rendered, and the server's
     * timezone is not the viewer's — formatting `new Date()` during render can
     * therefore produce a different string on each side and trip hydration.
     */
    const [today, setToday] = useState('')
    useEffect(() => setToday(formatHeaderDate(new Date())), [])

    return (
        <>
            <Toast toast={toast} onDismiss={dismiss} />

            <header className="section-head">
                <Reveal immediate>
                    {/* Non-breaking space holds the line so the heading does not shift. */}
                    <p className="dash-label mb-2">{today || '\u00A0'}</p>
                    <h1 className="section-title">Portfolio</h1>
                    <p className="section-lede">
                        Balances, positions and order flow, read straight from your connected Dhan account.
                    </p>
                </Reveal>
                <DhanConnect />
            </header>

            <PortfolioOverview />

            <footer className="mt-10 flex flex-col justify-between gap-2 border-t border-line pt-5 text-[10px] text-ink-tertiary sm:flex-row">
                <p>Figures are read directly from Dhan and are not recalculated here.</p>
                <p>Investments in securities markets are subject to market risks.</p>
            </footer>
        </>
    )
}

/** Matches the loaded layout so the hero does not jump into place. */
function DashboardFallback() {
    return (
        <>
            <div className="mb-7 flex flex-col justify-between gap-6 md:flex-row md:items-end">
                <div>
                    <Skeleton className="h-2.5 w-40" />
                    <Skeleton className="mt-3 h-8 w-52" delay={40} />
                    <Skeleton className="mt-3 h-2.5 w-72" delay={80} />
                </div>
                <Skeleton className="h-12 w-52 rounded-2xl" delay={120} />
            </div>
            <CellGrid className="grid-cols-2 lg:grid-cols-5">
                {[0, 1, 2, 3, 4].map((item) => (
                    <div key={item} className="p-5">
                        <Skeleton className="h-2.5 w-20" delay={item * 40} />
                        <Skeleton className="mt-4 h-5 w-24" delay={item * 40} />
                    </div>
                ))}
            </CellGrid>
            <Panel className="mt-4">
                <div className="panel-body">
                    <Skeleton className="h-40 w-full" />
                </div>
            </Panel>
        </>
    )
}

export default function DashboardPage() {
    return (
        <Suspense fallback={<DashboardFallback />}>
            <DashboardContent />
        </Suspense>
    )
}
