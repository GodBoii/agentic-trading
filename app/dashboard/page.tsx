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

export const dynamic = 'force-dynamic'

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
            setToastMessage('Connected Successfully!')
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
            <div className="min-h-screen bg-brutal-black flex items-center justify-center p-8">
                <div className="brutal-box p-12 text-center animate-pop">
                    <div className="inline-block animate-spin h-16 w-16 border-4 border-brutal-cream border-t-brutal-green mb-6"></div>
                    <p className="text-brutal-cream font-mono text-xl font-bold uppercase tracking-wider">Loading...</p>
                </div>
            </div>
        )
    }

    return (
        <div className="min-h-screen bg-brutal-black">
            {/* Toast Notification */}
            {showToast && (
                <div className="fixed top-8 right-8 z-50 animate-slide-in-right">
                    <div className={`brutal-box-sm p-6 flex items-center gap-4 ${toastType === 'success'
                        ? 'border-brutal-green shadow-brutal-green'
                        : 'border-brutal-red shadow-brutal-red'
                        }`}>
                        <div className={`w-3 h-3 ${toastType === 'success' ? 'bg-brutal-green' : 'bg-brutal-red'}`}></div>
                        <p className="font-bold text-brutal-cream uppercase tracking-wide text-sm">
                            {toastMessage}
                        </p>
                        <button
                            onClick={() => setShowToast(false)}
                            className="ml-4 text-brutal-cream hover:text-brutal-white transition-colors"
                            aria-label="Close notification"
                        >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M6 18L18 6M6 6l12 12" />
                            </svg>
                        </button>
                    </div>
                </div>
            )}

            {/* Header */}
            <header className="bg-brutal-black border-b-4 border-brutal-white sticky top-0 z-40">
                <div className="max-w-7xl mx-auto px-6 lg:px-8 py-5">
                    <div className="flex items-center justify-between">
                        {/* Logo — links back to homepage */}
                        <Link href="/" className="flex items-center gap-4 group" aria-label="Go to home page">
                            <div className="w-14 h-14 bg-brutal-cream border-4 border-brutal-black flex items-center justify-center p-2 group-hover:shadow-brutal-sm transition-all">
                                <img src="/icon.png" alt="Logo" className="w-full h-full object-contain" />
                            </div>
                            <div>
                                <h1 className="text-3xl font-bold text-brutal-cream uppercase tracking-tight group-hover:text-brutal-green transition-colors">
                                    Agentic Trading
                                </h1>
                                <p className="text-brutal-cream/50 font-mono text-xs uppercase tracking-widest mt-0.5">
                                    AI-Powered Platform
                                </p>
                            </div>
                        </Link>

                        <div className="flex items-center gap-6">
                            <div className="text-right hidden sm:block">
                                <p className="text-brutal-cream/60 font-mono text-xs uppercase tracking-wider">Logged in as</p>
                                <p className="text-brutal-cream font-mono font-bold text-sm truncate max-w-[200px]">
                                    {user?.email}
                                </p>
                            </div>
                            <button
                                onClick={handleSignOut}
                                id="dashboard-signout-btn"
                                className="brutal-btn px-6 py-3 text-sm"
                                aria-label="Sign out of your account"
                            >
                                Sign Out
                            </button>
                        </div>
                    </div>
                </div>
            </header>

            {/* Main Content */}
            <main className="max-w-7xl mx-auto px-6 lg:px-8 py-12">
                {/* Welcome Section */}
                <div className="mb-12">
                    <h2 className="text-5xl font-bold text-brutal-cream mb-4 uppercase tracking-tight">
                        Welcome Back
                    </h2>
                    <p className="text-brutal-cream/70 text-xl font-mono">
                        Manage your trading account
                    </p>
                </div>
                {/* Connect & Trading Status */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-12">
                    <DhanConnect />
                    <TradingStatus />
                </div>

                {/* Portfolio Section */}
                <div className="mb-12">
                    <div className="flex items-center gap-4 mb-8">
                        <div className="w-3 h-3 bg-brutal-green"></div>
                        <h2 className="text-3xl font-bold text-brutal-cream uppercase tracking-tight">
                            Portfolio Overview
                        </h2>
                    </div>

                    <div className="mb-8">
                        <FundsCard />
                    </div>

                    <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
                        <HoldingsCard />
                        <PositionsCard />
                    </div>
                </div>
            </main>
        </div>
    )
}

export default function DashboardPage() {
    return (
        <Suspense fallback={
            <div className="min-h-screen bg-brutal-black flex items-center justify-center p-8">
                <div className="brutal-box p-12 text-center animate-pop">
                    <div className="inline-block animate-spin h-16 w-16 border-4 border-brutal-cream border-t-brutal-green mb-6"></div>
                    <p className="text-brutal-cream font-mono text-xl font-bold uppercase tracking-wider">Loading...</p>
                </div>
            </div>
        }>
            <DashboardContent />
        </Suspense>
    )
}
