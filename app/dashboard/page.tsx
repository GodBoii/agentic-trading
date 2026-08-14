'use client'

import { Suspense, useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { AnimatePresence, motion } from 'framer-motion'
import DhanConnect from '@/components/dhan-connect'
import PortfolioOverview from '@/components/dashboard/portfolio-overview'
import { Skeleton } from '@/components/ui/skeleton'
import { CellGrid, Panel } from '@/components/ui/panel'
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
    const [toast, setToast] = useState<{ tone: 'success' | 'error'; message: string } | null>(null)

    // Surface the result of the Dhan OAuth round trip, then clean the URL so a
    // refresh does not replay the message.
    useEffect(() => {
        const success = searchParams.get('success')
        const error = searchParams.get('error')
        if (!success && !error) return

        setToast(
            success === 'true'
                ? { tone: 'success', message: 'Dhan account connected.' }
                : { tone: 'error', message: CONNECT_ERRORS[error || ''] || 'Unable to connect Dhan.' },
        )
        router.replace('/dashboard')
        const timer = window.setTimeout(() => setToast(null), 6000)
        return () => window.clearTimeout(timer)
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
            <AnimatePresence>
                {toast && (
                    <motion.div
                        role="status"
                        initial={{ opacity: 0, y: -8 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -8 }}
                        className={`fixed right-5 top-[68px] z-50 rounded-xl border px-4 py-3 text-[12px] shadow-2xl backdrop-blur-xl ${
                            toast.tone === 'success'
                                ? 'border-positive/25 bg-[#101713] text-positive'
                                : 'border-negative/25 bg-[#191111] text-negative'
                        }`}
                    >
                        {toast.message}
                    </motion.div>
                )}
            </AnimatePresence>

            <header className="mb-7 flex flex-col justify-between gap-6 md:flex-row md:items-end">
                <div>
                    {/* Non-breaking space holds the line so the heading does not shift. */}
                    <p className="dash-label mb-2">{today || '\u00A0'}</p>
                    <h1 className="text-[28px] font-medium leading-none tracking-[-0.04em] text-ink-primary sm:text-[34px]">
                        Portfolio
                    </h1>
                    <p className="mt-2.5 text-[12px] text-ink-tertiary">
                        Balances, positions and order flow from your connected Dhan account.
                    </p>
                </div>
                <DhanConnect />
            </header>

            <PortfolioOverview />

            <footer className="mt-8 flex flex-col justify-between gap-2 border-t border-line pt-5 text-[10px] text-ink-tertiary sm:flex-row">
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
                    <Skeleton className="mt-3 h-8 w-52" />
                    <Skeleton className="mt-3 h-2.5 w-72" />
                </div>
                <Skeleton className="h-12 w-52 rounded-2xl" />
            </div>
            <CellGrid className="grid-cols-2 lg:grid-cols-5">
                {[0, 1, 2, 3, 4].map((item) => (
                    <div key={item} className="p-5">
                        <Skeleton className="h-2.5 w-20" />
                        <Skeleton className="mt-4 h-5 w-24" />
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
