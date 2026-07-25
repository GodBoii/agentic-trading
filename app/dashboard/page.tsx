'use client'

import { Suspense, useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
import Link from 'next/link'
import DhanConnect from '@/components/dhan-connect'
import TradingStatus from '@/components/trading-status'
import FundsCard from '@/components/funds-card'
import HoldingsCard from '@/components/holdings-card'
import PositionsCard from '@/components/positions-card'
import { motion, AnimatePresence } from 'framer-motion'

export const dynamic = 'force-dynamic'

const ease = [0.16, 1, 0.3, 1] as const

function DashboardContent() {
    const router = useRouter()
    const searchParams = useSearchParams()
    const [showToast, setShowToast] = useState(false)
    const [toastMessage, setToastMessage] = useState('')
    const [toastType, setToastType] = useState<'success' | 'error'>('success')
    const [loading, setLoading] = useState(true)
    const [user, setUser] = useState<any>(null)
    const supabase = createClient()

    useEffect(() => {
        checkAuth()
    }, [])

    useEffect(() => {
        const success = searchParams.get('success')
        const error = searchParams.get('error')

        if (success === 'true') {
            setToastMessage('Connected Successfully')
            setToastType('success')
            setShowToast(true)
            router.replace('/dashboard')
            setTimeout(() => setShowToast(false), 5000)
        } else if (error) {
            const errorMessages: { [key: string]: string } = {
                'missing_token': 'Missing authentication token',
                'unauthorized': 'Please log in to continue',
                'server_config': 'Server configuration error',
                'token_exchange_failed': 'Failed to exchange token',
                'invalid_response': 'Invalid response',
                'db_save_failed': 'Failed to save credentials',
                'unexpected': 'An unexpected error occurred',
            }
            setToastMessage(errorMessages[error] || 'An error occurred')
            setToastType('error')
            setShowToast(true)
            router.replace('/dashboard')
            setTimeout(() => setShowToast(false), 5000)
        }
    }, [searchParams])

    const checkAuth = async () => {
        const { data: { user } } = await supabase.auth.getUser()
        if (!user) {
            router.push('/login')
            return
        }
        setUser(user)
        setLoading(false)
    }

    const handleSignOut = async () => {
        await supabase.auth.signOut()
        router.push('/')
    }

    const now = new Date()
    const greeting = now.getHours() < 12 ? 'Good morning' : now.getHours() < 18 ? 'Good afternoon' : 'Good evening'
    const dateStr = now.toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'short', year: 'numeric' })

    if (loading) {
        return (
            <div className="min-h-screen bg-[var(--dash-canvas)] flex items-center justify-center">
                <div className="flex flex-col items-center gap-4">
                    <div className="h-5 w-5 border border-[var(--accent)]/40 border-t-[var(--accent)] rounded-full animate-spin" />
                    <p className="dash-label">Loading</p>
                </div>
            </div>
        )
    }

    return (
        <div className="min-h-screen bg-[var(--dash-canvas)] text-white">
            {/* Toast */}
            <AnimatePresence>
                {showToast && (
                    <motion.div
                        initial={{ opacity: 0, y: -12 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -12 }}
                        transition={{ duration: 0.3, ease }}
                        className="fixed top-5 right-5 z-50"
                    >
                        <div className={`flex items-center gap-2.5 px-4 py-2.5 rounded-lg border backdrop-blur-xl ${
                            toastType === 'success'
                                ? 'border-[var(--dash-positive)]/20 bg-[var(--dash-positive)]/[0.06]'
                                : 'border-[var(--dash-negative)]/20 bg-[var(--dash-negative)]/[0.06]'
                        }`}>
                            <span className={`dash-dot ${toastType === 'success' ? 'dash-dot-positive' : 'dash-dot-negative'}`}
                                  style={{ width: 5, height: 5 }} />
                            <p className="text-[13px] text-[var(--dash-text)]">{toastMessage}</p>
                            <button
                                onClick={() => setShowToast(false)}
                                className="ml-2 text-[var(--dash-text-muted)] hover:text-white transition-colors"
                                aria-label="Close notification"
                            >
                                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                </svg>
                            </button>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Header */}
            <header className="sticky top-0 z-40 bg-[var(--dash-canvas)]/80 backdrop-blur-xl border-b border-[var(--dash-border)]">
                <div className="mx-auto max-w-6xl px-5 sm:px-6 h-14 flex items-center justify-between">
                    {/* Logo */}
                    <Link href="/" className="flex items-center gap-2" aria-label="Go to home page">
                        <div className="h-5 w-5 rounded-full bg-gradient-to-br from-[var(--accent)] to-[var(--dash-positive)] opacity-90" />
                        <span className="text-[14px] font-medium text-[var(--dash-text)] tracking-[-0.02em]">
                            Aetheria
                        </span>
                    </Link>

                    <div className="flex items-center gap-2">
                        <Link
                            href="/dashboard/ai-trading?view=trades"
                            className="dash-btn !text-[12px] !py-1.5 !px-3"
                        >
                            Trades
                        </Link>
                        <Link
                            href="/dashboard/ai-trading"
                            className="dash-btn !text-[12px] !py-1.5 !px-3"
                        >
                            Agent Chat
                        </Link>
                        <div className="w-px h-5 bg-[var(--dash-border)] mx-1 hidden sm:block" />
                        <button
                            onClick={handleSignOut}
                            id="dashboard-signout-btn"
                            className="dash-btn !text-[12px] !py-1.5 !px-3"
                            aria-label="Sign out of your account"
                        >
                            Sign Out
                        </button>
                    </div>
                </div>
            </header>

            {/* Main */}
            <main className="mx-auto max-w-6xl px-5 sm:px-6 py-10">
                {/* Greeting */}
                <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.5, ease }}
                    className="mb-10"
                >
                    <p className="text-[11px] font-mono text-[var(--dash-text-muted)] tracking-wide uppercase mb-2">
                        {dateStr}
                    </p>
                    <h1 className="text-[28px] sm:text-[32px] font-display text-[var(--dash-text)] tracking-[-0.03em] leading-tight">
                        {greeting}{user?.email ? ',' : '.'}{' '}
                        {user?.email && (
                            <span className="text-[var(--dash-text-secondary)]">
                                {user.email.split('@')[0]}
                            </span>
                        )}
                    </h1>
                </motion.div>

                {/* Connect & Trading Status */}
                <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.5, ease, delay: 0.08 }}
                    className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-10"
                >
                    <DhanConnect />
                    <TradingStatus />
                </motion.div>

                {/* Portfolio Section */}
                <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.5, ease, delay: 0.16 }}
                    className="space-y-4"
                >
                    <div className="flex items-center gap-3 mb-2">
                        <h2 className="text-[18px] font-display text-[var(--dash-text)] tracking-[-0.02em]">
                            Portfolio
                        </h2>
                        <div className="flex-1 h-px bg-[var(--dash-border)]" />
                    </div>

                    <FundsCard />

                    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                        <HoldingsCard />
                        <PositionsCard />
                    </div>
                </motion.div>
            </main>
        </div>
    )
}

export default function DashboardPage() {
    return (
        <Suspense fallback={
            <div className="min-h-screen bg-[var(--dash-canvas)] flex items-center justify-center">
                <div className="flex flex-col items-center gap-4">
                    <div className="h-5 w-5 border border-[var(--accent)]/40 border-t-[var(--accent)] rounded-full animate-spin" />
                    <p className="dash-label">Loading</p>
                </div>
            </div>
        }>
            <DashboardContent />
        </Suspense>
    )
}
