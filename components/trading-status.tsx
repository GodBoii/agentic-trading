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
            <div className="brutal-box p-8">
                <div className="animate-pulse space-y-4">
                    <div className="h-6 bg-brutal-cream/20 w-1/3"></div>
                    <div className="h-16 bg-brutal-cream/10"></div>
                </div>
            </div>
        )
    }

    if (!tradingKeys) {
        return (
            <div className="brutal-box p-8">
                <div className="flex items-center gap-4 mb-4">
                    <div className="w-3 h-3 bg-brutal-cream/50 flex-shrink-0"></div>
                    <div>
                        <h3 className="text-2xl font-bold text-brutal-cream uppercase tracking-tight">
                            Trading Status
                        </h3>
                        <p className="text-sm text-brutal-cream/60 font-mono mt-1">
                            Not Connected
                        </p>
                    </div>
                </div>
                <div className="brutal-box-sm border-brutal-cream/30 shadow-none p-6 text-center">
                    <p className="text-brutal-cream/70 font-mono text-sm">
                        Connect your Dhan account to enable trading
                    </p>
                </div>
            </div>
        )
    }

    const tokenExpired = isTokenExpired()

    return (
        <div className="brutal-box p-8 space-y-6">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <div className={`w-4 h-4 ${tradingKeys.is_trading_enabled
                            ? 'bg-brutal-green'
                            : 'bg-brutal-cream/50'
                        } flex-shrink-0`}></div>
                    <div>
                        <h3 className="text-2xl font-bold text-brutal-cream uppercase tracking-tight">
                            Trading Status
                        </h3>
                        <p className="text-sm text-brutal-cream/60 font-mono mt-1">
                            {tradingKeys.is_trading_enabled ? 'ACTIVE' : 'DISABLED'}
                        </p>
                    </div>
                </div>
            </div>

            {error && (
                <div className="brutal-box-sm border-brutal-red shadow-brutal-red p-4 animate-shake">
                    <p className="text-brutal-red font-mono text-sm font-bold uppercase">
                        {error}
                    </p>
                </div>
            )}

            {tokenExpired && (
                <div className="brutal-box-sm border-brutal-yellow shadow-none p-4">
                    <p className="text-brutal-yellow font-mono text-sm font-bold uppercase">
                        ⚠ Token expired. Please reconnect.
                    </p>
                </div>
            )}

            <div className="brutal-box-sm border-brutal-cream/30 shadow-none p-6 space-y-4">
                <div>
                    <p className="text-xs font-bold text-brutal-cream/60 mb-2 uppercase tracking-wider font-mono">
                        Client ID
                    </p>
                    <p className="text-xl font-mono text-brutal-cream font-bold">
                        {tradingKeys.dhan_client_id}
                    </p>
                </div>

                <div className="border-t-3 border-brutal-cream/20 pt-4">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-xs font-bold text-brutal-cream/60 mb-1 uppercase tracking-wider font-mono">
                                AI Trading
                            </p>
                            <p className="text-xs text-brutal-cream/50 font-mono">
                                {tradingKeys.is_trading_enabled
                                    ? 'AI can execute trades'
                                    : 'Trading is disabled'}
                            </p>
                        </div>
                        <button
                            onClick={handleToggle}
                            disabled={updating || tokenExpired}
                            className={`relative inline-flex h-10 w-20 items-center border-4 border-brutal-black transition-all disabled:opacity-50 disabled:cursor-not-allowed ${tradingKeys.is_trading_enabled
                                    ? 'bg-brutal-green'
                                    : 'bg-brutal-cream/20'
                                }`}
                            aria-label={`Toggle AI trading ${tradingKeys.is_trading_enabled ? 'off' : 'on'}`}
                            aria-pressed={tradingKeys.is_trading_enabled}
                        >
                            <span
                                className={`inline-block h-6 w-6 transform bg-brutal-black border-3 border-brutal-cream transition-transform ${tradingKeys.is_trading_enabled ? 'translate-x-11' : 'translate-x-1'
                                    }`}
                            />
                        </button>
                    </div>
                </div>
            </div>

            <div className="brutal-box-sm border-brutal-cream/30 shadow-none p-4">
                <div className="flex gap-3">
                    <div className="w-2 h-2 bg-brutal-green flex-shrink-0 mt-1"></div>
                    <div className="text-xs text-brutal-cream/70 font-mono leading-relaxed">
                        <p className="font-bold mb-2 uppercase tracking-wide">Safety First</p>
                        <p>
                            You can disable AI trading at any time. The system will only trade when enabled.
                        </p>
                    </div>
                </div>
            </div>
        </div>
    )
}
