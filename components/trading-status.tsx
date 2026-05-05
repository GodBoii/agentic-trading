'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'

interface TradingKeys {
    dhan_client_id: string
    dhan_access_token: string
    is_trading_enabled: boolean
    token_expiry: string
}

interface AgentRunStatus {
    status: string
    current_stage: string
    updated_at_utc?: string
    error?: string | null
    stages?: Record<string, { status: string; summary?: any }>
}

export default function TradingStatus() {
    const router = useRouter()
    const [tradingKeys, setTradingKeys] = useState<TradingKeys | null>(null)
    const [loading, setLoading] = useState(true)
    const [updating, setUpdating] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [runStatus, setRunStatus] = useState<AgentRunStatus | null>(null)
    const supabase = createClient()

    useEffect(() => {
        fetchTradingStatus()
        fetchRunStatus()
    }, [])

    useEffect(() => {
        const timer = setInterval(fetchRunStatus, 3000)
        return () => clearInterval(timer)
    }, [])

    const startAITrading = async () => {
        const response = await fetch('/api/ai-trading/toggle', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ enabled: true }),
        })

        if (!response.ok) {
            const payload = await response.json().catch(() => null)
            throw new Error(payload?.error || 'Failed to start AI trading')
        }
        const payload = await response.json()
        await fetchRunStatus()
        router.push(`/dashboard/ai-trading?run=${encodeURIComponent(payload?.request?.request_id || '')}`)
    }

    const fetchRunStatus = async () => {
        try {
            const response = await fetch('/api/ai-trading/toggle', { method: 'GET' })
            if (response.ok) {
                setRunStatus(await response.json())
            }
        } catch (statusError) {
            console.error('Error fetching AI trading run status:', statusError)
        }
    }

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

    const handleStart = async () => {
        if (!tradingKeys) return

        try {
            setUpdating(true)
            setError(null)

            await startAITrading()

            setTradingKeys({
                ...tradingKeys,
                is_trading_enabled: true,
            })
        } catch (err) {
            console.error('Error starting AI trading:', err)
            setError('Failed to start AI trading')
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
    const isRunning = runStatus?.status === 'running'
    const stageLabels: Record<string, string> = {
        stage2: 'Stage 2',
        stock_analyzer: 'Stock Analyzer',
        risk_analyzer: 'Risk Analyzer',
        executioner: 'Executioner',
    }

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
                            {isRunning ? 'RUNNING' : tradingKeys.is_trading_enabled ? 'READY' : 'IDLE'}
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
                                {isRunning
                                    ? 'Agents are running in order'
                                    : tradingKeys.is_trading_enabled
                                        ? 'Ready for the next user-started run'
                                        : 'Press start to run the agent chain'}
                            </p>
                        </div>
                        <button
                            onClick={handleStart}
                            disabled={updating || tokenExpired || isRunning}
                            className="brutal-btn px-5 py-3 text-xs disabled:opacity-50 disabled:cursor-not-allowed"
                            aria-label="Start AI trading"
                        >
                            {updating ? 'Starting...' : isRunning ? 'Running...' : 'Start AI Trading'}
                        </button>
                    </div>
                </div>
            </div>

            <div className="brutal-box-sm border-brutal-cream/30 shadow-none p-5 space-y-4">
                <div className="flex items-center justify-between gap-4">
                    <p className="text-xs font-bold text-brutal-cream/60 uppercase tracking-wider font-mono">
                        Agent Run
                    </p>
                    <p className="text-xs text-brutal-cream/60 font-mono uppercase">
                        {runStatus?.status || 'idle'}
                    </p>
                </div>

                <div className="space-y-3">
                    {Object.entries(stageLabels).map(([stage, label]) => {
                        const status = runStatus?.stages?.[stage]?.status || 'pending'
                        const active = status === 'running'
                        const complete = status === 'completed'
                        return (
                            <div key={stage} className="flex items-center justify-between gap-4 border-t-3 border-brutal-cream/10 pt-3 first:border-t-0 first:pt-0">
                                <div className="flex items-center gap-3">
                                    <div className={`w-3 h-3 ${complete ? 'bg-brutal-green' : active ? 'bg-brutal-yellow' : 'bg-brutal-cream/30'}`}></div>
                                    <p className="text-sm text-brutal-cream font-mono font-bold uppercase">
                                        {label}
                                    </p>
                                </div>
                                <p className="text-xs text-brutal-cream/60 font-mono uppercase">
                                    {status}
                                </p>
                            </div>
                        )
                    })}
                </div>

                {runStatus?.error && (
                    <p className="text-xs text-brutal-red font-mono font-bold uppercase">
                        {runStatus.error}
                    </p>
                )}
            </div>

            <div className="brutal-box-sm border-brutal-cream/30 shadow-none p-4">
                <div className="flex gap-3">
                    <div className="w-2 h-2 bg-brutal-green flex-shrink-0 mt-1"></div>
                    <div className="text-xs text-brutal-cream/70 font-mono leading-relaxed">
                        <p className="font-bold mb-2 uppercase tracking-wide">Safety First</p>
                        <p>
                            AI trading runs only when you press start. The agents execute once in order: stock analyzer, risk analyzer, then executioner.
                        </p>
                    </div>
                </div>
            </div>
        </div>
    )
}
