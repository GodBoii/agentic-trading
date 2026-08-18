'use client'

import { useEffect, useState } from 'react'
import { createClient } from '@/lib/supabase/client'
import { Button } from '@/components/ui/button'
import { Notice } from '@/components/ui/notice'
import { Panel, PanelBody, PanelFooter, PanelHeader } from '@/components/ui/panel'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { ErrorMessage, useErrorShake } from '@/components/motion/error-field'
import { SkeletonReveal } from '@/components/motion/skeleton-reveal'
import { SuccessCheck } from '@/components/motion/success-check'
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
 *
 * Motion. This is a form that commits a number affecting real money, so the
 * feedback is where the motion goes:
 *
 *   - An invalid amount shakes the field and reveals its message beneath it
 *     (recipe 12). Previously the validation message replaced the hint text in
 *     place and a red notice appeared at the bottom of the panel — easy to miss
 *     while the eye is still on the field that caused it. The shake puts the
 *     feedback where the problem is, and typing cancels it so the user is not
 *     shaking at a value they are already correcting.
 *
 *   - A successful save draws a check beside the button (recipe 10). Saving
 *     produced no acknowledgement at all before: the label reverted from
 *     "Saving" and the button greyed out because the form was no longer dirty,
 *     which is indistinguishable from the request having failed silently.
 *
 *   - The label swaps in place while saving (recipe 04), and the panel
 *     cross-fades in from its placeholder (recipe 14).
 */
export default function TradingStatus() {
    const [tradingKeys, setTradingKeys] = useState<TradingKeys | null>(null)
    const [tradeAmount, setTradeAmount] = useState('')
    const [status, setStatus] = useState<AmountStatus | null>(null)
    const [loading, setLoading] = useState(true)
    const [saving, setSaving] = useState(false)
    const [saved, setSaved] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const amount = useErrorShake<HTMLDivElement>()

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
        const parsed = trimmed === '' ? null : Number(trimmed)
        if (parsed !== null && (!Number.isFinite(parsed) || parsed <= 0)) {
            setError('Enter an amount greater than zero, or leave it blank for automatic sizing.')
            amount.trigger()
            return
        }
        try {
            setSaving(true)
            setSaved(false)
            setError(null)
            amount.clear()
            const response = await fetch('/api/ai-trading/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ trade_amount: parsed }),
            })
            const payload = await response.json().catch(() => null)
            if (!response.ok) throw new Error(payload?.error || 'Could not save your trading amount setting.')
            setStatus(payload)
            setTradeAmount(payload.trade_amount ? String(payload.trade_amount) : '')
            setSaved(true)
        } catch (saveError) {
            setError(saveError instanceof Error ? saveError.message : 'Could not save your trading amount setting.')
            amount.trigger()
        } finally {
            setSaving(false)
        }
    }

    if (!loading && !tradingKeys) {
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

    const tokenExpired = Boolean(tradingKeys?.token_expiry && new Date(tradingKeys.token_expiry) < new Date())
    const trimmed = tradeAmount.trim()
    const parsed = trimmed === '' ? null : Number(trimmed)
    const invalid = parsed !== null && (!Number.isFinite(parsed) || parsed <= 0)
    const automatic = trimmed === ''
    const dirty = String(status?.trade_amount ?? '') !== trimmed

    return (
        <SkeletonReveal loading={loading} skeleton={<SizingSkeleton />} label="Loading trade sizing" flow>
            <Panel aria-labelledby="sizing-title">
                <PanelHeader
                    titleId="sizing-title"
                    label="Trade sizing"
                    title="Capital per trade"
                    actions={
                        <Badge tone={automatic ? 'accent' : 'neutral'}>
                            {automatic ? 'Auto: available balance' : 'Fixed'}
                        </Badge>
                    }
                />
                <PanelBody className="space-y-5">
                    <p className="max-w-prose text-[12px] leading-relaxed text-ink-secondary">
                        Leave this blank to size automatically from the available balance at the moment of execution.
                        Enter an amount to cap it instead — the scanner will then only consider events your account can
                        afford; saving does not start a scan.
                    </p>

                    <div className={amount.wrapClass}>
                        <label htmlFor="trade-amount" className="dash-label">
                            Amount per trade
                        </label>
                        <div className="mt-2 flex items-center gap-2">
                            {/* The bordered wrapper is the shaking element, not
                                the input: the border is what changes tone, and
                                translating the input alone would slide the
                                currency glyph out of its own field. */}
                            <div ref={amount.fieldRef} className={`${amount.fieldClass} relative flex-1 rounded-lg`}>
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
                                    onChange={(event) => {
                                        setTradeAmount(event.target.value)
                                        setSaved(false)
                                        // Correcting the value clears the error
                                        // immediately rather than waiting out
                                        // the revert timer.
                                        amount.clear()
                                        setError(null)
                                    }}
                                    placeholder="Automatic — use available balance"
                                    disabled={tokenExpired}
                                    aria-label="Trading amount in rupees"
                                    aria-invalid={invalid || amount.errored}
                                    aria-describedby="trade-amount-hint trade-amount-error"
                                    className="dash-input dash-input-currency border-0 bg-transparent focus:shadow-none"
                                />
                            </div>
                            <span className="flex items-center gap-2">
                                <Button
                                    variant="solid"
                                    onClick={save}
                                    disabled={saving || invalid || tokenExpired || !dirty}
                                    swapLabel
                                >
                                    {saving ? 'Saving' : status?.configured ? 'Update' : 'Save'}
                                </Button>
                                {/* Persistent, not a toast: the confirmation
                                    belongs next to the control that produced
                                    it, and it clears on the next edit. */}
                                {saved && <SuccessCheck size={16} className="text-positive" />}
                            </span>
                        </div>

                        <ErrorMessage id="trade-amount-error">{error}</ErrorMessage>

                        <p id="trade-amount-hint" className="mt-1 text-[10px] text-ink-tertiary">
                            {automatic
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
                </PanelBody>
                {status?.amount_updated_at_utc && (
                    <PanelFooter>
                        <p className="text-[10px] text-ink-tertiary">
                            Last changed{' '}
                            <span className="font-mono">{formatDateTime(status.amount_updated_at_utc)}</span>
                        </p>
                    </PanelFooter>
                )}
            </Panel>
        </SkeletonReveal>
    )
}

function SizingSkeleton() {
    return (
        <Panel>
            <div className="panel-header">
                <Skeleton className="h-3.5 w-44" />
            </div>
            <div className="panel-body space-y-4">
                <Skeleton className="h-2.5 w-full max-w-md" delay={40} />
                <Skeleton className="h-9 w-full" delay={80} />
                <Skeleton className="h-10 w-full" delay={120} />
            </div>
        </Panel>
    )
}
