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

const stageLabels: Record<string, string> = {
    stage2: 'Stage 2',
    stock_analyzer: 'Stock Analyzer',
    executioner: 'Executioner',
}

export default function TradingStatus() {
    const router = useRouter()
    const [tradingKeys, setTradingKeys] = useState<TradingKeys | null>(null)
    const [loading, setLoading] = useState(true)
    const [updating, setUpdating] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [runStatus, setRunStatus] = useState<AgentRunStatus | null>(null)
    const [tradeMode, setTradeMode] = useState<'auto' | 'manual'>('auto')
    const [tradeAmount, setTradeAmount] = useState<string>('')
    const [regimeAnalysisEnabled, setRegimeAnalysisEnabled] = useState(true)
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
        const payload: Record<string, any> = {
            enabled: true,
            trade_mode: tradeMode,
            regime_analysis_enabled: regimeAnalysisEnabled,
        }
        if (tradeMode === 'manual') {
            const amount = parseFloat(tradeAmount)
            if (!amount || amount <= 0) {
                throw new Error('Please enter a valid trade amount')
            }
            payload.trade_amount = amount
        }

        const response = await fetch('/api/ai-trading/toggle', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload),
        })

        if (!response.ok) {
            const errPayload = await response.json().catch(() => null)
            throw new Error(errPayload?.error || 'Failed to start AI trading')
        }
        const resPayload = await response.json()
        await fetchRunStatus()
        router.push(`/dashboard/ai-trading?run=${encodeURIComponent(resPayload?.request?.request_id || '')}`)
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
            <div className="surface rounded-2xl p-7 lg:p-8 h-full">
                <div className="animate-pulse space-y-4">
                    <div className="h-3 w-24 bg-white/[0.06] rounded-full" />
                    <div className="h-6 w-40 bg-white/[0.04] rounded" />
                    <div className="h-32 bg-white/[0.03] rounded-xl mt-6" />
                </div>
            </div>
        )
    }

    if (!tradingKeys) {
        return (
            <div className="surface rounded-2xl p-7 lg:p-8 h-full flex flex-col">
                <div className="flex items-start justify-between mb-6">
                    <div>
                        <span className="text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary">
                            Agent · Engine
                        </span>
                        <h3 className="font-display text-[24px] lg:text-[26px] text-white tracking-[-0.025em] leading-[1.1] mt-2">
                            Trading Status
                        </h3>
                    </div>
                </div>
                <p className="text-[13px] text-ink-secondary leading-relaxed mb-7">
                    Connect your Dhan account to enable live trading, AI agent orchestration, and real-time execution.
                </p>
                <div className="mt-auto border border-dashed border-line rounded-xl px-5 py-8 text-center">
                    <p className="text-[12px] text-ink-tertiary font-mono">
                        Awaiting broker connection
                    </p>
                </div>
            </div>
        )
    }

    const tokenExpired = isTokenExpired()
    const isRunning = runStatus?.status === 'running'
    const isActive = isRunning || tradingKeys.is_trading_enabled

    return (
        <div className="surface rounded-2xl p-7 lg:p-8 h-full flex flex-col">
            {/* Header */}
            <div className="flex items-start justify-between mb-7">
                <div>
                    <span className="text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary">
                        Agent · Engine
                    </span>
                    <h3 className="font-display text-[24px] lg:text-[26px] text-white tracking-[-0.025em] leading-[1.1] mt-2">
                        Trading Status
                    </h3>
                </div>
                <div className="flex items-center gap-2 mt-1">
                    <span className={`relative flex h-1.5 w-1.5`}>
                        <span className={`absolute inline-flex h-full w-full rounded-full ${isRunning ? 'bg-warning' : isActive ? 'bg-success' : 'bg-ink-tertiary'} opacity-60 animate-pulse-ring`} />
                        <span className={`relative inline-flex h-1.5 w-1.5 rounded-full ${isRunning ? 'bg-warning' : isActive ? 'bg-success' : 'bg-ink-tertiary'}`} />
                    </span>
                    <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-ink-tertiary">
                        {isRunning ? 'Running' : tradingKeys.is_trading_enabled ? 'Ready' : 'Idle'}
                    </span>
                </div>
            </div>

            {error && (
                <div className="mb-6 border border-danger/40 bg-danger/[0.06] rounded-xl px-4 py-3">
                    <p className="text-danger font-mono text-[12px] font-medium">
                        {error}
                    </p>
                </div>
            )}

            {tokenExpired && (
                <div className="mb-6 border border-warning/40 bg-warning/[0.06] rounded-xl px-4 py-3">
                    <p className="text-warning font-mono text-[12px] font-medium">
                        Token expired. Please reconnect.
                    </p>
                </div>
            )}

            {/* Client ID */}
            <div className="mb-6 pb-6 border-b border-line">
                <p className="text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary mb-2">
                    Client ID
                </p>
                <p className="text-[18px] font-mono text-white font-medium nums">
                    {tradingKeys.dhan_client_id}
                </p>
            </div>

            {/* Trade Amount */}
            <div className="mb-6">
                <p className="text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary mb-3">
                    Trade Amount
                </p>
                <div className="flex items-center gap-2 mb-4">
                    <button
                        onClick={() => setTradeMode('auto')}
                        className={`text-[11px] font-mono uppercase tracking-[0.15em] px-4 py-2 rounded-full border transition-all duration-300 ease-out-expo ${tradeMode === 'auto'
                            ? 'border-accent/50 bg-accent/10 text-white'
                            : 'border-line text-ink-tertiary hover:border-line-strong hover:text-ink-secondary'
                            }`}
                    >
                        Auto
                    </button>
                    <button
                        onClick={() => setTradeMode('manual')}
                        className={`text-[11px] font-mono uppercase tracking-[0.15em] px-4 py-2 rounded-full border transition-all duration-300 ease-out-expo ${tradeMode === 'manual'
                            ? 'border-accent/50 bg-accent/10 text-white'
                            : 'border-line text-ink-tertiary hover:border-line-strong hover:text-ink-secondary'
                            }`}
                    >
                        Manual
                    </button>
                </div>
                {tradeMode === 'manual' ? (
                    <div className="flex items-center gap-2 bg-[#0a0a0c] border border-line hover:border-line-strong focus-within:border-accent/60 rounded-xl px-4 py-3 transition-all duration-300">
                        <span className="text-ink-secondary font-mono text-[14px]">₹</span>
                        <input
                            type="number"
                            min="1"
                            step="1"
                            value={tradeAmount}
                            onChange={(e) => setTradeAmount(e.target.value)}
                            placeholder="Enter amount (e.g. 500)"
                            className="w-full bg-transparent text-white font-mono text-[14px] placeholder:text-ink-tertiary focus:outline-none"
                        />
                    </div>
                ) : (
                    <p className="text-[12px] text-ink-tertiary leading-relaxed">
                        Uses your available balance to select stocks and size trades automatically.
                    </p>
                )}
            </div>

            {/* Regime Gate */}
            <div className="mb-6 pb-6 border-b border-line">
                <div className="flex items-center justify-between gap-4">
                    <div>
                        <p className="text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary mb-1">
                            Regime Analysis
                        </p>
                        <p className="text-[12px] text-ink-secondary leading-relaxed">
                            {regimeAnalysisEnabled
                                ? 'Market regime context will be supplied to the stock analyzer.'
                                : 'Agents will run without regime context.'}
                        </p>
                    </div>
                    <button
                        type="button"
                        onClick={() => setRegimeAnalysisEnabled((value) => !value)}
                        disabled={updating || isRunning}
                        className={`relative h-7 w-12 rounded-full border transition-all duration-300 disabled:opacity-40 disabled:cursor-not-allowed ${regimeAnalysisEnabled
                            ? 'border-success/50 bg-success/20'
                            : 'border-line bg-[#0a0a0c]'
                            }`}
                        aria-pressed={regimeAnalysisEnabled}
                        aria-label="Toggle regime analysis"
                    >
                        <span
                            className={`absolute top-1 h-5 w-5 rounded-full transition-all duration-300 ${regimeAnalysisEnabled
                                ? 'left-6 bg-success'
                                : 'left-1 bg-ink-tertiary'
                                }`}
                        />
                    </button>
                </div>
            </div>

            {/* Start Button */}
            <div className="flex items-center justify-between gap-4 mb-7 pb-7 border-b border-line">
                <div className="flex-1">
                    <p className="text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary mb-1">
                        AI Trading
                    </p>
                    <p className="text-[12px] text-ink-secondary leading-relaxed">
                        {isRunning
                            ? 'Agents are running in order'
                            : tradingKeys.is_trading_enabled
                                ? 'Ready for the next run'
                                : 'Press start to run the chain'}
                    </p>
                </div>
                <button
                    onClick={handleStart}
                    disabled={updating || tokenExpired || isRunning || (tradeMode === 'manual' && (!tradeAmount || parseFloat(tradeAmount) <= 0))}
                    className="btn-primary !px-5 !py-2.5 !text-[12px] disabled:opacity-30 disabled:cursor-not-allowed disabled:transform-none disabled:hover:shadow-none"
                    aria-label="Start AI trading"
                >
                    {updating ? 'Starting…' : isRunning ? 'Running…' : 'Start Agent'}
                </button>
            </div>

            {/* Agent Run Stages */}
            <div className="space-y-4 mb-7 flex-1">
                <div className="flex items-center justify-between">
                    <p className="text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary">
                        Agent Run
                    </p>
                    <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-ink-tertiary">
                        {runStatus?.status || 'idle'}
                    </p>
                </div>

                <div className="space-y-2.5">
                    {Object.entries(stageLabels).map(([stage, label]) => {
                        const status = runStatus?.stages?.[stage]?.status || 'pending'
                        const active = status === 'running'
                        const complete = status === 'completed'
                        return (
                            <div
                                key={stage}
                                className="flex items-center justify-between gap-4 py-2.5 px-3.5 rounded-lg bg-white/[0.015] border border-line/50 hover:border-line transition-colors"
                            >
                                <div className="flex items-center gap-3">
                                    <div className={`h-1.5 w-1.5 rounded-full ${complete ? 'bg-success' : active ? 'bg-warning animate-pulse-soft' : 'bg-ink-tertiary'}`} />
                                    <p className="text-[12px] text-white font-mono font-medium">
                                        {label}
                                    </p>
                                </div>
                                <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-ink-tertiary">
                                    {status}
                                </p>
                            </div>
                        )
                    })}
                </div>

                {runStatus?.error && (
                    <p className="text-[11px] text-danger font-mono pt-2">
                        {runStatus.error}
                    </p>
                )}
            </div>

            {/* Safety Note */}
            <div className="pt-6 border-t border-line">
                <div className="flex gap-3">
                    <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-success flex-shrink-0" />
                    <div>
                        <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-ink-tertiary mb-1.5">
                            Safety First
                        </p>
                        <p className="text-[12px] text-ink-secondary leading-relaxed">
                            AI trading runs only when you press start. The agents execute once in order: analyzer, then executioner.
                        </p>
                    </div>
                </div>
            </div>
        </div>
    )
}
