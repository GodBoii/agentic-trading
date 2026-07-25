'use client'

import { Suspense, useEffect, useMemo, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { AnimatePresence, motion } from 'framer-motion'
import { createClient } from '@/lib/supabase/client'
import DhanConnect from '@/components/dhan-connect'
import PortfolioOverview from '@/components/portfolio-overview'

export const dynamic = 'force-dynamic'

function DashboardContent() {
    const router = useRouter()
    const searchParams = useSearchParams()
    const [loading, setLoading] = useState(true)
    const [userEmail, setUserEmail] = useState('')
    const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null)

    useEffect(() => {
        const checkAuth = async () => {
            const supabase = createClient()
            const { data: { user } } = await supabase.auth.getUser()
            if (!user) {
                router.push('/login')
                return
            }
            setUserEmail(user.email || '')
            setLoading(false)
        }
        checkAuth()
    }, [router])

    useEffect(() => {
        const success = searchParams.get('success')
        const error = searchParams.get('error')
        if (!success && !error) return

        const messages: Record<string, string> = {
            missing_token: 'Dhan did not return an authentication token.',
            unauthorized: 'Please sign in before connecting Dhan.',
            server_config: 'The Dhan connection is not configured on the server.',
            token_exchange_failed: 'Dhan could not complete the token exchange.',
            invalid_response: 'Dhan returned an invalid response.',
            db_save_failed: 'The connection could not be saved.',
            unexpected: 'An unexpected connection error occurred.',
        }
        setToast(success === 'true'
            ? { type: 'success', message: 'Dhan account connected successfully.' }
            : { type: 'error', message: messages[error || ''] || 'Unable to connect Dhan.' })
        router.replace('/dashboard')
        const timer = window.setTimeout(() => setToast(null), 5000)
        return () => window.clearTimeout(timer)
    }, [router, searchParams])

    const date = useMemo(() => new Intl.DateTimeFormat('en-IN', {
        weekday: 'long',
        day: 'numeric',
        month: 'long',
    }).format(new Date()), [])

    const handleSignOut = async () => {
        const supabase = createClient()
        await supabase.auth.signOut()
        router.push('/')
    }

    if (loading) return <DashboardLoader />

    return (
        <div className="product-shell min-h-screen bg-[var(--dash-canvas)] text-white">
            <AnimatePresence>
                {toast && (
                    <motion.div
                        initial={{ opacity: 0, y: -10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -10 }}
                        className={`fixed right-4 top-4 z-50 rounded-xl border px-4 py-3 text-[12px] shadow-2xl backdrop-blur-xl ${
                            toast.type === 'success'
                                ? 'border-[var(--dash-positive)]/20 bg-[#101713] text-[var(--dash-positive)]'
                                : 'border-[var(--dash-negative)]/20 bg-[#191111] text-[var(--dash-negative)]'
                        }`}
                    >
                        {toast.message}
                    </motion.div>
                )}
            </AnimatePresence>

            <header className="sticky top-0 z-40 border-b border-[var(--dash-border)] bg-[#09090b]/90 backdrop-blur-xl">
                <div className="mx-auto flex h-16 max-w-[1320px] items-center justify-between px-5 sm:px-8">
                    <Link href="/" className="flex items-center gap-2.5" aria-label="Polycognitive home">
                        <span className="grid h-7 w-7 place-items-center rounded-lg border border-white/10 bg-white/[0.04]">
                            <span className="h-1.5 w-1.5 rounded-full bg-[#37d67a] shadow-[0_0_12px_rgba(55,214,122,0.7)]" />
                        </span>
                        <span className="text-[13px] font-medium tracking-[-0.02em]">Polycognitive</span>
                        <span className="hidden border-l border-white/10 pl-2.5 font-mono text-[8px] uppercase tracking-[0.18em] text-[var(--dash-text-muted)] sm:inline">
                            Portfolio
                        </span>
                    </Link>

                    <nav className="flex items-center gap-1.5" aria-label="Dashboard navigation">
                        <Link href="/dashboard/ai-trading?view=trades" className="dash-btn !border-transparent !px-3 !py-1.5 !text-[11px]">Trades</Link>
                        <Link href="/dashboard/ai-trading" className="dash-btn !border-transparent !px-3 !py-1.5 !text-[11px]">Agent</Link>
                        <button onClick={handleSignOut} className="dash-btn !ml-1 !px-3 !py-1.5 !text-[11px]">Sign out</button>
                    </nav>
                </div>
            </header>

            <main className="mx-auto max-w-[1320px] px-5 py-9 sm:px-8 sm:py-12">
                <section className="mb-10 flex flex-col justify-between gap-7 md:flex-row md:items-end">
                    <div>
                        <p className="mb-2 font-mono text-[9px] uppercase tracking-[0.14em] text-[var(--dash-text-muted)]">{date}</p>
                        <h1 className="text-[30px] font-medium leading-none tracking-[-0.045em] text-[var(--dash-text)] sm:text-[38px]">
                            Your portfolio
                        </h1>
                        <p className="mt-3 text-[12px] text-[var(--dash-text-muted)]">
                            {userEmail} · Live account intelligence
                        </p>
                    </div>
                    <DhanConnect />
                </section>

                <PortfolioOverview />

                <footer className="mt-8 flex flex-col justify-between gap-2 border-t border-[var(--dash-border)] pt-5 text-[9px] text-[var(--dash-text-muted)] sm:flex-row">
                    <p>Values are sourced from your connected Dhan account.</p>
                    <p>Investments in securities markets are subject to market risks.</p>
                </footer>
            </main>
        </div>
    )
}

function DashboardLoader() {
    return (
        <div className="product-shell grid min-h-screen place-items-center bg-[var(--dash-canvas)]">
            <div className="flex items-center gap-3">
                <span className="h-2 w-2 animate-pulse rounded-full bg-[#37d67a]" />
                <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-[var(--dash-text-muted)]">Loading portfolio</span>
            </div>
        </div>
    )
}

export default function DashboardPage() {
    return (
        <Suspense fallback={<DashboardLoader />}>
            <DashboardContent />
        </Suspense>
    )
}
