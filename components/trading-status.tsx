'use client'

import { useEffect, useState } from 'react'
import { createClient } from '@/lib/supabase/client'

interface TradingKeys { token_expiry: string | null }
interface AmountStatus {
    configured?: boolean
    eligible: boolean
    trade_mode?: 'auto' | 'manual'
    status_code: string
    message: string
    trade_amount: number | null
}
export default function TradingStatus() {
    const [tradingKeys, setTradingKeys] = useState<TradingKeys | null>(null)
    const [tradeAmount, setTradeAmount] = useState('')
    const [status, setStatus] = useState<AmountStatus | null>(null)
    const [loading, setLoading] = useState(true)
    const [saving, setSaving] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const supabase = createClient()

    useEffect(() => {
        const load = async () => {
            try {
                const { data: { user } } = await supabase.auth.getUser()
                if (!user) throw new Error('Not authenticated')
                const { data, error: keysError } = await supabase.from('user_trading_keys').select('token_expiry').eq('user_id', user.id).single()
                if (keysError && keysError.code !== 'PGRST116') throw keysError
                setTradingKeys(data || null)
                const response = await fetch('/api/ai-trading/config', { cache: 'no-store' })
                if (!response.ok) throw new Error('Could not load your trading amount setting.')
                const loaded = await response.json()
                setStatus(loaded)
                setTradeAmount(loaded.trade_amount ? String(loaded.trade_amount) : '')
            } catch (loadError) {
                setError(loadError instanceof Error ? loadError.message : 'Could not load trading settings.')
            } finally { setLoading(false) }
        }
        load()
    }, [])

    const saveAmount = async () => {
        const trimmed = tradeAmount.trim()
        const amount = trimmed === '' ? null : Number(trimmed)
        if (amount !== null && (!Number.isFinite(amount) || amount <= 0)) {
            setError('Enter an amount greater than zero, or leave it blank for automatic sizing.')
            return
        }
        try {
            setSaving(true)
            setError(null)
            const response = await fetch('/api/ai-trading/config', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ trade_amount: amount }),
            })
            const payload = await response.json().catch(() => null)
            if (!response.ok) throw new Error(payload?.error || 'Could not save your trading amount setting.')
            setStatus(payload)
            setTradeAmount(payload.trade_amount ? String(payload.trade_amount) : '')
        } catch (saveError) {
            setError(saveError instanceof Error ? saveError.message : 'Could not save your trading amount setting.')
        } finally { setSaving(false) }
    }

    if (loading) return <div className="dash-surface h-56 animate-pulse" />
    if (!tradingKeys) return (
        <div className="dash-surface p-6">
            <span className="dash-label">Trading amount</span>
            <h3 className="mt-1 text-[22px] font-display text-[var(--dash-text)]">Connect your broker</h3>
            <p className="mt-3 text-[13px] leading-relaxed text-[var(--dash-text-secondary)]">Connect your Dhan account, then optionally set a fixed amount. If left blank, sizing uses available balance automatically.</p>
        </div>
    )

    const tokenExpired = Boolean(tradingKeys.token_expiry && new Date(tradingKeys.token_expiry) < new Date())
    const trimmed = tradeAmount.trim()
    const amount = trimmed === '' ? null : Number(trimmed)
    const invalid = amount !== null && (!Number.isFinite(amount) || amount <= 0)
    return (
        <div className="dash-surface p-6">
            <span className="dash-label">Trading amount</span>
            <h3 className="mt-1 text-[24px] font-display tracking-[-0.035em] text-[var(--dash-text)]">Optional per-trade amount</h3>
            <p className="mt-2 text-[13px] leading-relaxed text-[var(--dash-text-secondary)]">Leave this blank to size automatically from current available balance. Enter an amount to filter and size affordable Stage 2 events for your account. Market monitoring is continuous; saving does not start a scan.</p>
            <label className="mt-6 block">
                <span className="dash-label">Amount in rupees (optional)</span>
                <div className="mt-2 flex items-center gap-2">
                    <span className="font-mono text-[15px] text-[var(--dash-text-secondary)]">₹</span>
                    <input aria-label="Trading amount in rupees" type="number" min="0.01" step="0.01" inputMode="decimal" value={tradeAmount} onChange={(event) => setTradeAmount(event.target.value)} placeholder="Auto: available balance" className="dash-input" />
                    <button type="button" onClick={saveAmount} disabled={saving || invalid || tokenExpired} className="dash-btn-primary !px-5 !py-2.5 !text-[12px]">
                        {saving ? 'Saving…' : status?.configured ? 'Update' : 'Save'}
                    </button>
                </div>
            </label>
            <div className={`mt-5 rounded-lg border px-3 py-2.5 ${status?.eligible ? 'border-[rgba(52,211,153,0.18)] bg-[rgba(52,211,153,0.04)]' : 'border-[rgba(251,191,36,0.18)] bg-[rgba(251,191,36,0.04)]'}`}>
                <p className={`font-mono text-[11px] ${status?.eligible ? 'text-[var(--dash-positive)]' : 'text-[var(--dash-warning)]'}`}>
                    {tokenExpired ? 'Broker token expired. Agent and order dispatch are paused for your account while market monitoring continues.' : status?.message || 'Leave blank for automatic balance sizing, or enter a fixed amount.'}
                </p>
            </div>
            {error && <p className="mt-3 font-mono text-[11px] text-[var(--dash-negative)]">{error}</p>}
        </div>
    )
}
