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
    stock_agent: 'Stock Agent',
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
            <div className="dash-surface p-6 h-full">
                <div className="animate-pulse space-y-3">
                    <div className="h-3 w-20 bg-white/[0.04] rounded" />
                    <div className="h-5 w-32 bg-white/[0.03] rounded" />
                    <div className="h-24 bg-white/[0.02] rounded mt-4" />
                </div>
            </div>
        )
    }

    if (!tradingKeys) {
        return (
            <div className="dash-surface p-6 h-full flex flex-col">
                <div className="mb-4">
                    <span className="dash-label">Agent Engine</span>
                    <h3 className="text-[20px] font-display text-[var(--dash-text)] tracking-[-0.02em] mt-1">
                        Trading Status
                    </h3>
                </div>
                <p className="text-[13px] text-[var(--dash-text-secondary)] leading-relaxed mb-6">
                    Connect your Dhan account to enable AI agent orchestration.
                </p>
                <div className="mt-auto rounded-xl border border-dashed border-[var(--dash-border)] py-8 text-center">
                    <p className="text-[12px] text-[var(--dash-text-muted)] font-mono">
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
        <div className="dash-surface p-6 h-full flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between mb-5">
                <div>
                    <span className="dash-label">Agent Engine</span>
                    <h3 className="text-[20px] font-display text-[var(--dash-text)] tracking-[-0.02em] mt-1">
                        Trading Status
                    </h3>
                </div>
                <span className={`dash-badge ${isRunning ? 'dash-badge-warning' : isActive ? 'dash-badge-positive' : ''}`}>
                    <span className={`dash-dot ${isRunning ? 'dash-dot-warning dash-dot-pulse' : isActive ? 'dash-dot-positive' : 'dash-dot-muted'}`}
                          style={{ width: 5, height: 5 }} />
                    {isRunning ? 'Running' : tradingKeys.is_trading_enabled ? 'Ready' : 'Idle'}
                </span>
            </div>

            {/* Alerts */}
            {error && (
                <div className="mb-4 px-3 py-2.5 rounded-lg bg-[rgba(248,113,113,0.04)] border border-[rgba(248,113,113,0.15)]">
                    <p className="text-[var(--dash-negative)] font-mono text-[12px]">{error}</p>
                </div>
            )}
            {tokenExpired && (
                <div className="mb-4 px-3 py-2.5 rounded-lg bg-[rgba(251,191,36,0.04)] border border-[rgba(251,191,36,0.15)]">
                    <p className="text-[var(--dash-warning)] font-mono text-[12px]">Token expired — please reconnect.</p>
                </div>
            )}

            {/* Client ID */}
            <div className="mb-5 pb-4 border-b border-[var(--dash-border)]">
                <p className="dash-label mb-1">Client ID</p>
                <p className="text-[16px] font-mono text-[var(--dash-text)] font-medium nums">
                    {tradingKeys.dhan_client_id}
                </p>
            </div>

            {/* Trade Config */}
            <div className="space-y-4 mb-5">
                {/* Mode selector */}
                <div>
                    <p className="dash-label mb-2">Trade Amount</p>
                    <div className="flex gap-1.5">
                        <button
                            onClick={() => setTradeMode('auto')}
                            className={`text-[12px] font-mono px-3 py-1.5 rounded-md transition-all duration-200 ${
                                tradeMode === 'auto'
                                    ? 'bg-[var(--accent)]/10 text-[var(--accent)] border border-[var(--accent)]/25'
                                    : 'text-[var(--dash-text-muted)] border border-[var(--dash-border)] hover:text-[var(--dash-text-secondary)]'
                            }`}
                        >
                            Auto
                        </button>
                        <button
                            onClick={() => setTradeMode('manual')}
                            className={`text-[12px] font-mono px-3 py-1.5 rounded-md transition-all duration-200 ${
                                tradeMode === 'manual'
                                    ? 'bg-[var(--accent)]/10 text-[var(--accent)] border border-[var(--accent)]/25'
                                    : 'text-[var(--dash-text-muted)] border border-[var(--dash-border)] hover:text-[var(--dash-text-secondary)]'
                            }`}
                        >
                            Manual
                        </button>
                    </div>
                    {tradeMode === 'manual' ? (
                        <div className="flex items-center gap-2 mt-2">
                            <span className="text-[var(--dash-text-secondary)] font-mono text-[13px]">₹</span>
                            <input
                                type="number"
                                min="1"
                                step="1"
                                value={tradeAmount}
                                onChange={(e) => setTradeAmount(e.target.value)}
                                placeholder="500"
                                className="dash-input !py-1.5"
                            />
                        </div>
                    ) : (
                        <p className="text-[11px] text-[var(--dash-text-muted)] mt-2 leading-relaxed">
                            Auto-sizes trades from available balance.
                        </p>
                    )}
                </div>

                {/* Regime toggle */}
                <div className="flex items-center justify-between gap-3">
                    <div>
                        <p className="text-[12px] text-[var(--dash-text-secondary)]">Regime Analysis</p>
                        <p className="text-[11px] text-[var(--dash-text-muted)]">
                            {regimeAnalysisEnabled ? 'Enabled' : 'Disabled'}
                        </p>
                    </div>
                    <button
                        type="button"
                        onClick={() => setRegimeAnalysisEnabled((v) => !v)}
                        disabled={updating || isRunning}
                        className="dash-toggle"
                        aria-pressed={regimeAnalysisEnabled}
                        aria-label="Toggle regime analysis"
                    />
                </div>
            </div>

            {/* Start Action */}
            <div className="flex items-center justify-between gap-3 mb-5 pb-4 border-b border-[var(--dash-border)]">
                <div>
                    <p className="text-[12px] text-[var(--dash-text-secondary)]">
                        {isRunning ? 'Agents are running' : 'Press start to run agents'}
                    </p>
                </div>
                <button
                    onClick={handleStart}
                    disabled={updating || tokenExpired || isRunning || (tradeMode === 'manual' && (!tradeAmount || parseFloat(tradeAmount) <= 0))}
                    className="dash-btn-primary !text-[12px] !px-4 !py-2"
                    aria-label="Start AI trading"
                >
                    {updating ? 'Starting…' : isRunning ? 'Running…' : 'Start Agent'}
                </button>
            </div>

            {/* Agent Stages */}
            <div className="flex-1 space-y-3">
                <p className="dash-label">Agent Run</p>
                <div className="space-y-1.5">
                    {Object.entries(stageLabels).map(([stage, label]) => {
                        const status = runStatus?.stages?.[stage]?.status || 'pending'
                        const active = status === 'running'
                        const complete = status === 'completed'
                        return (
                            <div
                                key={stage}
                                className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-white/[0.01] transition-colors"
                            >
                                <div className="flex items-center gap-2.5">
                                    <span className={`dash-dot ${complete ? 'dash-dot-positive' : active ? 'dash-dot-warning dash-dot-pulse' : 'dash-dot-muted'}`} />
                                    <span className="text-[12px] font-mono text-[var(--dash-text)]">{label}</span>
                                </div>
                                <span className="dash-label">{status}</span>
                            </div>
                        )
                    })}
                </div>
                {runStatus?.error && (
                    <p className="text-[11px] text-[var(--dash-negative)] font-mono mt-1">
                        {runStatus.error}
                    </p>
                )}
            </div>

            {/* Safety note */}
            <p className="mt-4 pt-3 border-t border-[var(--dash-border)] text-[11px] text-[var(--dash-text-muted)] leading-relaxed">
                AI trading runs only when you press start. Agents analyze and execute once.
            </p>
        </div>
    )
}
