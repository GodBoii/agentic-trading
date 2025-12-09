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
        // Check for success or error in URL params
        const success = searchParams.get('success')
        const error = searchParams.get('error')

        if (success === 'true') {
            setToastMessage('Account Connected Successfully! 🎉')
            setToastType('success')
            setShowToast(true)

            // Clean up URL
            router.replace('/dashboard')

            setTimeout(() => setShowToast(false), 5000)
        } else if (error) {
            const errorMessages: { [key: string]: string } = {
                'missing_token': 'Missing authentication token',
                'unauthorized': 'Please log in to continue',
                'server_config': 'Server configuration error',
                'token_exchange_failed': 'Failed to exchange token with Dhan',
                'invalid_response': 'Invalid response from Dhan',
                'db_save_failed': 'Failed to save credentials',
                'unexpected': 'An unexpected error occurred',
            }

            setToastMessage(errorMessages[error] || 'An error occurred')
            setToastType('error')
            setShowToast(true)

            // Clean up URL
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
            <div className="min-h-screen bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-50 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900 flex items-center justify-center">
                <div className="text-center">
                    <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-blue-600 border-t-transparent"></div>
                    <p className="mt-4 text-gray-600 dark:text-gray-400">Loading...</p>
                </div>
            </div>
        )
    }

    return (
        <div className="min-h-screen bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-50 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900">
            {/* Toast Notification */}
            {showToast && (
                <div className="fixed top-4 right-4 z-50 animate-slide-in-right">
                    <div className={`rounded-lg shadow-2xl px-6 py-4 flex items-center gap-3 ${toastType === 'success'
                        ? 'bg-green-50 dark:bg-green-900/20 border-2 border-green-500'
                        : 'bg-red-50 dark:bg-red-900/20 border-2 border-red-500'
                        }`}>
                        {toastType === 'success' ? (
                            <svg className="w-6 h-6 text-green-600 dark:text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                            </svg>
                        ) : (
                            <svg className="w-6 h-6 text-red-600 dark:text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                            </svg>
                        )}
                        <p className={`font-semibold ${toastType === 'success'
                            ? 'text-green-800 dark:text-green-300'
                            : 'text-red-800 dark:text-red-300'
                            }`}>
                            {toastMessage}
                        </p>
                        <button
                            onClick={() => setShowToast(false)}
                            className="ml-4 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
                        >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                            </svg>
                        </button>
                    </div>
                </div>
            )}

            {/* Header */}
            <header className="bg-white/80 dark:bg-gray-800/80 backdrop-blur-lg border-b border-gray-200 dark:border-gray-700 sticky top-0 z-40">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <div className="inline-flex items-center justify-center w-10 h-10 bg-gradient-to-br from-blue-600 to-indigo-600 rounded-lg">
                                <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                                </svg>
                            </div>
                            <div>
                                <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
                                    Agentic Trading
                                </h1>
                                <p className="text-sm text-gray-600 dark:text-gray-400">
                                    AI-Powered Trading Dashboard
                                </p>
                            </div>
                        </div>

                        <div className="flex items-center gap-4">
                            <div className="text-right">
                                <p className="text-sm text-gray-600 dark:text-gray-400">Logged in as</p>
                                <p className="text-sm font-semibold text-gray-900 dark:text-white">
                                    {user?.email}
                                </p>
                            </div>
                            <button
                                onClick={handleSignOut}
                                className="px-4 py-2 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-900 dark:text-white rounded-lg transition-all font-medium"
                            >
                                Sign Out
                            </button>
                        </div>
                    </div>
                </div>
            </header>

            {/* Main Content */}
            <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                {/* Welcome Section */}
                <div className="mb-8">
                    <h2 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
                        Welcome Back! 👋
                    </h2>
                    <p className="text-gray-600 dark:text-gray-400">
                        Manage your trading account and let AI handle the rest
                    </p>
                </div>

                {/* Grid Layout */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
                    {/* Connect Component */}
                    <DhanConnect />

                    {/* Status Component */}
                    <TradingStatus />
                </div>

                {/* Portfolio Section */}
                <div className="mb-8">
                    <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">
                        📊 Portfolio Overview
                    </h2>

                    {/* Account Funds */}
                    <div className="mb-6">
                        <FundsCard />
                    </div>

                    {/* Holdings & Positions Grid */}
                    <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 mb-6">
                        <HoldingsCard />
                        <PositionsCard />
                    </div>
                </div>

                {/* Info Cards */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-md p-6">
                        <div className="flex items-center gap-3 mb-3">
                            <div className="w-10 h-10 bg-purple-100 dark:bg-purple-900/20 rounded-lg flex items-center justify-center">
                                <svg className="w-6 h-6 text-purple-600 dark:text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                                </svg>
                            </div>
                            <h3 className="text-lg font-bold text-gray-900 dark:text-white">
                                AI-Powered
                            </h3>
                        </div>
                        <p className="text-sm text-gray-600 dark:text-gray-400">
                            Multi-agent system analyzes markets 24/7 using technical and sentiment analysis
                        </p>
                    </div>

                    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-md p-6">
                        <div className="flex items-center gap-3 mb-3">
                            <div className="w-10 h-10 bg-green-100 dark:bg-green-900/20 rounded-lg flex items-center justify-center">
                                <svg className="w-6 h-6 text-green-600 dark:text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                                </svg>
                            </div>
                            <h3 className="text-lg font-bold text-gray-900 dark:text-white">
                                Secure
                            </h3>
                        </div>
                        <p className="text-sm text-gray-600 dark:text-gray-400">
                            Bank-level encryption with Supabase RLS ensures your credentials are protected
                        </p>
                    </div>

                    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-md p-6">
                        <div className="flex items-center gap-3 mb-3">
                            <div className="w-10 h-10 bg-blue-100 dark:bg-blue-900/20 rounded-lg flex items-center justify-center">
                                <svg className="w-6 h-6 text-blue-600 dark:text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                                </svg>
                            </div>
                            <h3 className="text-lg font-bold text-gray-900 dark:text-white">
                                Automated
                            </h3>
                        </div>
                        <p className="text-sm text-gray-600 dark:text-gray-400">
                            Set it and forget it. The AI executes trades automatically when opportunities arise
                        </p>
                    </div>
                </div>

                {/* How It Works Section */}
                <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-lg p-8">
                    <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">
                        How It Works
                    </h3>

                    <div className="space-y-6">
                        <div className="flex gap-4">
                            <div className="flex-shrink-0 w-10 h-10 bg-blue-600 text-white rounded-full flex items-center justify-center font-bold">
                                1
                            </div>
                            <div>
                                <h4 className="font-semibold text-gray-900 dark:text-white mb-1">
                                    Connect Your Account
                                </h4>
                                <p className="text-gray-600 dark:text-gray-400">
                                    Enter your Dhan Client ID and securely link your trading account
                                </p>
                            </div>
                        </div>

                        <div className="flex gap-4">
                            <div className="flex-shrink-0 w-10 h-10 bg-indigo-600 text-white rounded-full flex items-center justify-center font-bold">
                                2
                            </div>
                            <div>
                                <h4 className="font-semibold text-gray-900 dark:text-white mb-1">
                                    Enable AI Trading
                                </h4>
                                <p className="text-gray-600 dark:text-gray-400">
                                    Toggle the trading switch to allow the AI to execute trades on your behalf
                                </p>
                            </div>
                        </div>

                        <div className="flex gap-4">
                            <div className="flex-shrink-0 w-10 h-10 bg-purple-600 text-white rounded-full flex items-center justify-center font-bold">
                                3
                            </div>
                            <div>
                                <h4 className="font-semibold text-gray-900 dark:text-white mb-1">
                                    Sit Back & Relax
                                </h4>
                                <p className="text-gray-600 dark:text-gray-400">
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
            <div className="min-h-screen bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-50 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900 flex items-center justify-center">
                <div className="text-center">
                    <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-blue-600 border-t-transparent"></div>
                    <p className="mt-4 text-gray-600 dark:text-gray-400">Loading...</p>
                </div>
            </div>
        }>
            <DashboardContent />
        </Suspense>
    )
}
