'use client'

import { useEffect, useState } from 'react'
import { createClient } from '@/lib/supabase/client'
import { Button } from '@/components/ui/button'
import { Notice } from '@/components/ui/notice'
import { Panel, PanelBody, PanelFooter, PanelHeader } from '@/components/ui/panel'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { formatDateTime, money } from '@/lib/format'

interface TradingKeys {
    token_expiry: string | null
}

interface AmountStatus {
    configured?: boolean
    eligible: boolean
    trade_mode?: 'auto' | 'manual'
    status_code: string
    message: string
    trade_amount: number | null
    amount_updated_at_utc?: string
}

/**
 * Per-trade capital sizing.
 *
 * Blank means "size from available balance at execution time"; a value fixes
 * the amount. That distinction drives which trades the scanner considers
 * affordable, so the resolved mode is stated explicitly rather than left
 * implied by an empty input.
 */
export default function TradingStatus() {
    const [tradingKeys, setTradingKeys] = useState<TradingKeys | null>(null)
    const [tradeAmount, setTradeAmount] = useState('')
    const [status, setStatus] = useState<AmountStatus | null>(null)
    const [loading, setLoading] = useState(true)
    const [saving, setSaving] = useState(false)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        const load = async () => {
            const supabase = createClient()
            try {
                const {
                    data: { user },
                } = await supabase.auth.getUser()
                if (!user) throw new Error('Not authenticated')

                const { data, error: keysError } = await supabase
                    .from('user_trading_keys')
                    .select('token_expiry')
                    .eq('user_id', user.id)
                    .single()
                // PGRST116 is "no rows", which simply means no broker linked yet.
                if (keysError && keysError.code !== 'PGRST116') throw keysError
                setTradingKeys(data || null)

                const response = await fetch('/api/ai-trading/config', { cache: 'no-store' })
                if (!response.ok) throw new Error('Could not load your trading amount setting.')
                const loaded: AmountStatus = await response.json()
                setStatus(loaded)
                setTradeAmount(loaded.trade_amount ? String(loaded.trade_amount) : '')
            } catch (loadError) {
                setError(loadError instanceof Error ? loadError.message : 'Could not load trading settings.')
            } finally {
                setLoading(false)
            }
        }
        void load()
    }, [])

    const save = async () => {
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
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ trade_amount: amount }),
            })
            const payload = await response.json().catch(() => null)
            if (!response.ok) throw new Error(payload?.error || 'Could not save your trading amount setting.')
            setStatus(payload)
            setTradeAmount(payload.trade_amount ? String(payload.trade_amount) : '')
        } catch (saveError) {
            setError(saveError instanceof Error ? saveError.message : 'Could not save your trading amount setting.')
        } finally {
            setSaving(false)
        }
    }

    if (loading) {
        return (
            <Panel>
                <div className="panel-header">
                    <Skeleton className="h-3.5 w-44" />
                </div>
                <div className="panel-body space-y-4">
                    <Skeleton className="h-2.5 w-full max-w-md" />
                    <Skeleton className="h-9 w-full" />
                    <Skeleton className="h-10 w-full" />
                </div>
            </Panel>
        )
    }

    if (!tradingKeys) {
        return (
            <Panel>
                <PanelHeader label="Trade sizing" title="Connect your broker first" />
                <PanelBody>
                    <p className="text-[12px] leading-relaxed text-ink-secondary">
                        Link your Dhan account from the Portfolio screen. Once connected you can leave sizing automatic
                        or fix an amount per trade.
                    </p>
                </PanelBody>
            </Panel>
        )
    }

    const tokenExpired = Boolean(tradingKeys.token_expiry && new Date(tradingKeys.token_expiry) < new Date())
    const trimmed = tradeAmount.trim()
    const parsed = trimmed === '' ? null : Number(trimmed)
    const invalid = parsed !== null && (!Number.isFinite(parsed) || parsed <= 0)
    const automatic = trimmed === ''
    const dirty = String(status?.trade_amount ?? '') !== trimmed

    return (
        <Panel aria-labelledby="sizing-title">
            <PanelHeader
                titleId="sizing-title"
                label="Trade sizing"
                title="Capital per trade"
                actions={
                    <Badge tone={automatic ? 'accent' : 'neutral'}>{automatic ? 'Automatic' : 'Fixed'}</Badge>
                }
            />
            <PanelBody className="space-y-5">
                <p className="max-w-prose text-[12px] leading-relaxed text-ink-secondary">
                    Leave this blank to size each trade from the available balance at the moment of execution. Enter an
                    amount to cap it instead — the scanner will then only consider events your account can afford.
                    Saving does not trigger a scan.
                </p>

                <div>
                    <label htmlFor="trade-amount" className="dash-label">
                        Amount per trade
                    </label>
                    <div className="mt-2 flex items-center gap-2">
                        <div className="relative flex-1">
                            <span
                                aria-hidden
                                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 font-mono text-[13px] text-ink-tertiary"
                            >
                                ₹
                            </span>
                            <input
                                id="trade-amount"
                                type="number"
                                min="0.01"
                                step="0.01"
                                inputMode="decimal"
                                value={tradeAmount}
                                onChange={(event) => setTradeAmount(event.target.value)}
                                placeholder="Automatic — use available balance"
                                disabled={tokenExpired}
                                aria-invalid={invalid}
                                aria-describedby="trade-amount-hint"
                                className="dash-input dash-input-currency"
                            />
                        </div>
                        <Button
                            variant="solid"
                            onClick={save}
                            disabled={saving || invalid || tokenExpired || !dirty}
                        >
                            {saving ? 'Saving' : status?.configured ? 'Update' : 'Save'}
                        </Button>
                    </div>
                    <p id="trade-amount-hint" className="mt-2 text-[10px] text-ink-tertiary">
                        {invalid
                            ? 'Enter an amount greater than zero, or clear the field for automatic sizing.'
                            : automatic
                              ? 'Blank field means automatic sizing from available balance.'
                              : `Each trade will use up to ${money(parsed || 0)}.`}
                    </p>
                </div>

                {tokenExpired ? (
                    <Notice tone="danger">
                        Your broker token has expired. Order dispatch is paused for your account while market
                        monitoring continues. Reconnect Dhan from the Portfolio screen to resume.
                    </Notice>
                ) : (
                    <Notice tone={status?.eligible ? 'neutral' : 'warning'}>
                        {status?.message || 'Leave blank for automatic balance sizing, or enter a fixed amount.'}
                    </Notice>
                )}

                {error && <Notice tone="danger">{error}</Notice>}
            </PanelBody>
            {status?.amount_updated_at_utc && (
                <PanelFooter>
                    <p className="text-[10px] text-ink-tertiary">
                        Last changed <span className="font-mono">{formatDateTime(status.amount_updated_at_utc)}</span>
                    </p>
                </PanelFooter>
            )}
        </Panel>
    )
}
