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
import { motion } from 'framer-motion'

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

    if (loading) {
        return (
            <div className="min-h-screen bg-[#050505] flex items-center justify-center">
                <div className="flex flex-col items-center gap-5">
                    <div className="relative h-10 w-10">
                        <span className="absolute inline-flex h-full w-full rounded-full bg-accent opacity-40 animate-pulse-ring" />
                        <span className="relative inline-flex h-10 w-10 rounded-full border border-accent/40" />
                    </div>
                    <p className="text-[11px] font-mono uppercase tracking-[0.22em] text-ink-tertiary">
                        Initializing terminal
                    </p>
                </div>
            </div>
        )
    }

    return (
        <div className="relative min-h-screen bg-[#050505] text-white overflow-x-hidden">
            {/* Ambient backdrop */}
            <div className="pointer-events-none fixed inset-0 bg-grid-fine opacity-50" />
            <div className="pointer-events-none fixed inset-0 bg-spotlight" />

            {/* Toast Notification */}
            {showToast && (
                <motion.div
                    initial={{ opacity: 0, y: -16, x: 0 }}
                    animate={{ opacity: 1, y: 0, x: 0 }}
                    transition={{ duration: 0.5, ease }}
                    className="fixed top-24 right-6 z-50"
                >
                    <div className={`glass rounded-2xl px-5 py-4 flex items-center gap-3 min-w-[300px] ${toastType === 'success'
                        ? 'border-success/40'
                        : 'border-danger/40'
                        }`}>
                        <div className="relative flex h-2 w-2">
                            <span className={`absolute inline-flex h-full w-full rounded-full ${toastType === 'success' ? 'bg-success' : 'bg-danger'} opacity-60 animate-pulse-ring`} />
                            <span className={`relative inline-flex h-2 w-2 rounded-full ${toastType === 'success' ? 'bg-success' : 'bg-danger'}`} />
                        </div>
                        <p className="text-[13px] font-medium text-white flex-1">
                            {toastMessage}
                        </p>
                        <button
                            onClick={() => setShowToast(false)}
                            className="text-ink-tertiary hover:text-white transition-colors"
                            aria-label="Close notification"
                        >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                            </svg>
                        </button>
                    </div>
                </motion.div>
            )}

            {/* Header */}
            <header className="sticky top-0 z-40">
                <div className="mx-auto max-w-7xl px-4 sm:px-6 pt-5">
                    <div className="glass rounded-full px-5 sm:px-6 py-3 flex items-center justify-between">
                        {/* Logo */}
                        <Link href="/" className="group flex items-center gap-2.5" aria-label="Go to home page">
                            <div className="relative h-7 w-7">
                                <div className="absolute inset-0 rounded-full bg-gradient-to-br from-accent to-success opacity-80 blur-md group-hover:opacity-100 transition-opacity" />
                                <div className="absolute inset-[3px] rounded-full bg-[#0a0a0c] flex items-center justify-center">
                                    <div className="h-1.5 w-1.5 rounded-full bg-white" />
                                </div>
                            </div>
                            <span className="text-[15px] font-medium tracking-[-0.02em] text-white">
                                Aetheria
                            </span>
                            <span className="hidden sm:inline-block text-[10px] font-mono uppercase tracking-[0.2em] text-white/40 pl-2 border-l border-white/10 ml-1">
                                Terminal
                            </span>
                        </Link>

                        <div className="flex items-center gap-3 sm:gap-4">
                            <div className="text-right hidden sm:block">
                                <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-ink-tertiary">
                                    Authenticated
                                </p>
                                <p className="text-[12px] font-mono text-white truncate max-w-[200px]">
                                    {user?.email}
                                </p>
                            </div>
                            <button
                                onClick={handleSignOut}
                                id="dashboard-signout-btn"
                                className="btn-secondary !px-4 !py-1.5 !text-[12px]"
                                aria-label="Sign out of your account"
                            >
                                Sign Out
                            </button>
                        </div>
                    </div>
                </div>
            </header>

            {/* Main Content */}
            <main className="relative mx-auto max-w-7xl px-6 lg:px-8 pt-12 pb-24">
                {/* Welcome Section */}
                <motion.div
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.8, ease, delay: 0.1 }}
                    className="mb-14"
                >
                    <div className="inline-flex items-center gap-2 mb-5">
                        <span className="h-px w-8 bg-accent" />
                        <span className="text-[11px] font-mono uppercase tracking-[0.22em] text-accent">
                            Live Terminal
                        </span>
                    </div>
                    <h1 className="font-display text-display-md text-white mb-4">
                        Welcome back, <span className="font-serif-italic text-ink-secondary">operator</span>.
                    </h1>
                    <p className="text-[15px] text-ink-secondary max-w-xl">
                        Manage your trading account, monitor live positions, and orchestrate AI agents from a single command surface.
                    </p>
                </motion.div>

                {/* Connect & Trading Status */}
                <motion.div
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.8, ease, delay: 0.2 }}
                    className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-20"
                >
                    <DhanConnect />
                    <TradingStatus />
                </motion.div>

                {/* Portfolio Section */}
                <motion.div
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.8, ease, delay: 0.3 }}
                    className="space-y-8"
                >
                    <div className="flex items-end justify-between flex-wrap gap-4 pb-6 border-b border-line">
                        <div>
                            <div className="inline-flex items-center gap-2 mb-4">
                                <span className="h-px w-8 bg-accent" />
                                <span className="text-[11px] font-mono uppercase tracking-[0.22em] text-accent">
                                    Portfolio
                                </span>
                            </div>
                            <h2 className="font-display text-display-sm text-white">
                                Capital overview
                            </h2>
                        </div>
                    </div>

                    <FundsCard />

                    <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
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
            <div className="min-h-screen bg-[#050505] flex items-center justify-center">
                <div className="flex flex-col items-center gap-5">
                    <div className="relative h-10 w-10">
                        <span className="absolute inline-flex h-full w-full rounded-full bg-accent opacity-40 animate-pulse-ring" />
                        <span className="relative inline-flex h-10 w-10 rounded-full border border-accent/40" />
                    </div>
                    <p className="text-[11px] font-mono uppercase tracking-[0.22em] text-ink-tertiary">
                        Initializing terminal
                    </p>
                </div>
            </div>
        }>
            <DashboardContent />
        </Suspense>
    )
}
