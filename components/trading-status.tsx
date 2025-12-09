'use client'

import { useState, useEffect } from 'react'
import { createClient } from '@/lib/supabase/client'

interface TradingKeys {
    dhan_client_id: string
    dhan_access_token: string
    is_trading_enabled: boolean
    token_expiry: string
}

export default function TradingStatus() {
    const [tradingKeys, setTradingKeys] = useState<TradingKeys | null>(null)
    const [loading, setLoading] = useState(true)
    const [updating, setUpdating] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const supabase = createClient()

    // Fetch trading status on component mount
    useEffect(() => {
        fetchTradingStatus()
    }, [])

    const fetchTradingStatus = async () => {
        try {
            setLoading(true)
            const { data: { user } } = await supabase.auth.getUser()

            if (!user) {
                setError('Not authenticated')
                return
            }

            const { data, error: fetchError } = await supabase
                .from('user_trading_keys')
                .select('dhan_client_id, dhan_access_token, is_trading_enabled, token_expiry')
                .eq('user_id', user.id)
                .single()

            if (fetchError) {
                if (fetchError.code === 'PGRST116') {
                    // No row found - user hasn't connected yet
                    setTradingKeys(null)
                } else {
                    console.error('Error fetching trading keys:', fetchError)
                    setError('Failed to load trading status')
                }
            } else {
                setTradingKeys(data)
            }
        } catch (err) {
            console.error('Error:', err)
            setError('An unexpected error occurred')
        } finally {
            setLoading(false)
        }
    }

    const handleToggle = async () => {
        if (!tradingKeys) return

        try {
            setUpdating(true)
            setError(null)

            const newStatus = !tradingKeys.is_trading_enabled

            const { error: updateError } = await supabase
                .from('user_trading_keys')
                .update({ is_trading_enabled: newStatus })
                .eq('user_id', (await supabase.auth.getUser()).data.user?.id)

            if (updateError) {
                throw updateError
            }

            // Update local state
            setTradingKeys({
                ...tradingKeys,
                is_trading_enabled: newStatus,
            })
        } catch (err) {
            console.error('Error toggling trading:', err)
            setError('Failed to update trading status')
        } finally {
            setUpdating(false)
        }
    }

    const isTokenExpired = () => {
        if (!tradingKeys?.token_expiry) return false
        return new Date(tradingKeys.token_expiry) < new Date()
    }

    if (loading) {
        return (
            <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-lg p-6">
                <div className="animate-pulse space-y-4">
                    <div className="h-6 bg-gray-200 dark:bg-gray-700 rounded w-1/3"></div>
                    <div className="h-16 bg-gray-200 dark:bg-gray-700 rounded"></div>
                </div>
            </div>
        )
    }

    if (!tradingKeys) {
        return (
            <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-lg p-6">
                <div className="flex items-center gap-3 mb-4">
                    <div className="inline-flex items-center justify-center w-12 h-12 bg-gray-100 dark:bg-gray-700 rounded-full">
                        <svg
                            className="w-6 h-6 text-gray-400"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                        >
                            <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                            />
                        </svg>
                    </div>
                    <div>
                        <h3 className="text-xl font-bold text-gray-900 dark:text-white">
                            Trading Status
                        </h3>
                        <p className="text-sm text-gray-600 dark:text-gray-400">
                            Not Connected
                        </p>
                    </div>
                </div>
                <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 text-center">
                    <p className="text-gray-600 dark:text-gray-400">
                        Connect your Dhan account to enable trading
                    </p>
                </div>
            </div>
        )
    }

    const tokenExpired = isTokenExpired()

    return (
        <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-lg p-6 space-y-4">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className={`inline-flex items-center justify-center w-12 h-12 rounded-full ${tradingKeys.is_trading_enabled
                            ? 'bg-gradient-to-br from-green-500 to-emerald-600'
                            : 'bg-gradient-to-br from-gray-400 to-gray-500'
                        }`}>
                        <svg
                            className="w-6 h-6 text-white"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                        >
                            <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                            />
                        </svg>
                    </div>
                    <div>
                        <h3 className="text-xl font-bold text-gray-900 dark:text-white">
                            Trading Status
                        </h3>
                        <p className="text-sm text-gray-600 dark:text-gray-400">
                            Connected ✅
                        </p>
                    </div>
                </div>
            </div>

            {error && (
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-600 dark:text-red-400 px-4 py-3 rounded-lg text-sm">
                    {error}
                </div>
            )}

            {tokenExpired && (
                <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 text-yellow-800 dark:text-yellow-400 px-4 py-3 rounded-lg text-sm">
                    ⚠️ Your access token has expired. Please reconnect your account.
                </div>
            )}

            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 space-y-3">
                <div className="flex items-center justify-between">
                    <div>
                        <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                            Client ID
                        </p>
                        <p className="text-lg font-mono text-gray-900 dark:text-white">
                            {tradingKeys.dhan_client_id}
                        </p>
                    </div>
                </div>

                <div className="border-t border-gray-200 dark:border-gray-600 pt-3">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                AI Trading
                            </p>
                            <p className="text-xs text-gray-500 dark:text-gray-400">
                                {tradingKeys.is_trading_enabled
                                    ? 'AI can execute trades on your behalf'
                                    : 'Trading is currently disabled'}
                            </p>
                        </div>
                        <button
                            onClick={handleToggle}
                            disabled={updating || tokenExpired}
                            className={`relative inline-flex h-8 w-14 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed ${tradingKeys.is_trading_enabled
                                    ? 'bg-gradient-to-r from-green-500 to-emerald-600'
                                    : 'bg-gray-300 dark:bg-gray-600'
                                }`}
                        >
                            <span
                                className={`inline-block h-6 w-6 transform rounded-full bg-white shadow-lg transition-transform ${tradingKeys.is_trading_enabled ? 'translate-x-7' : 'translate-x-1'
                                    }`}
                            />
                        </button>
                    </div>
                </div>
            </div>

            <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
                <div className="flex gap-3">
                    <svg
                        className="w-5 h-5 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                    >
                        <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                        />
                    </svg>
                    <div className="text-sm text-blue-800 dark:text-blue-300">
                        <p className="font-semibold mb-1">Safety First</p>
                        <p className="text-blue-700 dark:text-blue-400">
                            You can disable AI trading at any time. The system will only trade when enabled.
                        </p>
                    </div>
                </div>
            </div>
        </div>
    )
}
