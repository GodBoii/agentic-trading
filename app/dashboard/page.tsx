'use client'

import { Suspense, useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
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
        router.push('/login')
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
                <div className="max-w-7xl mx-auto px-6 lg:px-8 py-6">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-6">
                            <div className="w-16 h-16 bg-brutal-cream border-4 border-brutal-black flex items-center justify-center">
                                <svg className="w-8 h-8 text-brutal-black" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={3}>
                                    <path strokeLinecap="square" strokeLinejoin="miter" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                                </svg>
                            </div>
                            <div>
                                <h1 className="text-4xl font-bold text-brutal-cream uppercase tracking-tight">
                                    Agentic Trading
                                </h1>
                                <p className="text-brutal-cream/70 font-mono text-sm uppercase tracking-wider mt-1">
                                    AI-Powered Platform
                                </p>
                            </div>
                        </div>

                        <div className="flex items-center gap-6">
                            <div className="text-right">
                                <p className="text-brutal-cream/60 font-mono text-xs uppercase tracking-wider">Logged in</p>
                                <p className="text-brutal-cream font-mono font-bold">
                                    {user?.email}
                                </p>
                            </div>
                            <button
                                onClick={handleSignOut}
                                className="brutal-btn px-6 py-3 text-sm"
                                aria-label="Sign out"
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

                {/* Grid Layout */}
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

                {/* Info Cards */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12">
                    <div className="brutal-box p-8">
                        <div className="flex items-start gap-4 mb-4">
                            <div className="w-4 h-4 bg-brutal-green flex-shrink-0 mt-1"></div>
                            <h3 className="text-2xl font-bold text-brutal-cream uppercase">
                                AI-Powered
                            </h3>
                        </div>
                        <p className="text-brutal-cream/70 leading-relaxed font-mono text-sm">
                            Multi-agent system analyzes markets 24/7 using technical and sentiment analysis
                        </p>
                    </div>

                    <div className="brutal-box p-8">
                        <div className="flex items-start gap-4 mb-4">
                            <div className="w-4 h-4 bg-brutal-cream flex-shrink-0 mt-1"></div>
                            <h3 className="text-2xl font-bold text-brutal-cream uppercase">
                                Secure
                            </h3>
                        </div>
                        <p className="text-brutal-cream/70 leading-relaxed font-mono text-sm">
                            Bank-level encryption with Supabase RLS ensures your credentials are protected
                        </p>
                    </div>

                    <div className="brutal-box p-8">
                        <div className="flex items-start gap-4 mb-4">
                            <div className="w-4 h-4 bg-brutal-yellow flex-shrink-0 mt-1"></div>
                            <h3 className="text-2xl font-bold text-brutal-cream uppercase">
                                Automated
                            </h3>
                        </div>
                        <p className="text-brutal-cream/70 leading-relaxed font-mono text-sm">
                            Set it and forget it. The AI executes trades automatically when opportunities arise
                        </p>
                    </div>
                </div>

                {/* How It Works Section */}
                <div className="brutal-box-lg p-10">
                    <h3 className="text-3xl font-bold text-brutal-cream mb-10 uppercase tracking-tight">
                        How It Works
                    </h3>

                    <div className="space-y-8">
                        <div className="flex gap-6">
                            <div className="flex-shrink-0 w-12 h-12 bg-brutal-cream text-brutal-black flex items-center justify-center font-bold text-xl border-3 border-brutal-black">
                                1
                            </div>
                            <div>
                                <h4 className="font-bold text-brutal-cream mb-2 text-xl uppercase">
                                    Connect Your Account
                                </h4>
                                <p className="text-brutal-cream/70 font-mono">
                                    Enter your Dhan Client ID and securely link your trading account
                                </p>
                            </div>
                        </div>

                        <div className="flex gap-6">
                            <div className="flex-shrink-0 w-12 h-12 bg-brutal-green text-brutal-black flex items-center justify-center font-bold text-xl border-3 border-brutal-black">
                                2
                            </div>
                            <div>
                                <h4 className="font-bold text-brutal-cream mb-2 text-xl uppercase">
                                    Enable AI Trading
                                </h4>
                                <p className="text-brutal-cream/70 font-mono">
                                    Toggle the trading switch to allow the AI to execute trades on your behalf
                                </p>
                            </div>
                        </div>

                        <div className="flex gap-6">
                            <div className="flex-shrink-0 w-12 h-12 bg-brutal-yellow text-brutal-black flex items-center justify-center font-bold text-xl border-3 border-brutal-black">
                                3
                            </div>
                            <div>
                                <h4 className="font-bold text-brutal-cream mb-2 text-xl uppercase">
                                    Sit Back & Relax
                                </h4>
                                <p className="text-brutal-cream/70 font-mono">
                                    Our multi-agent AI system analyzes the market and executes profitable trades automatically
                                </p>
                            </div>
                        </div>
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
