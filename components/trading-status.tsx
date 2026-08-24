'use client'

import { useEffect, useState } from 'react'
import { createClient } from '@/lib/supabase/client'
import { Button } from '@/components/ui/button'
import { Notice } from '@/components/ui/notice'
import { Panel, PanelBody, PanelFooter, PanelHeader } from '@/components/ui/panel'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { SegmentedChoice, type TabItem } from '@/components/ui/tabs'
import { DisclosurePanel } from '@/components/motion/accordion'
import { ErrorMessage, useErrorShake } from '@/components/motion/error-field'
import { NumberFlow } from '@/components/motion/number-flow'
import { SkeletonReveal } from '@/components/motion/skeleton-reveal'
import { SuccessCheck } from '@/components/motion/success-check'
import { formatDateTime, money } from '@/lib/format'
import { autoSlotAmount, fixedSlotCount, parseSlotCount } from '@/lib/trade-sizing'
import type { Funds } from '@/components/dashboard/types'

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
    /** Slots auto mode budgets for. Older API responses use the shared fallback. */
    auto_slots?: number
    max_leverage?: number
    order_placement?: {
        allowed: boolean
        status_code: string
        reason: string
        verified_at_utc: string | null
        next_verification_at_utc: string | null
        detected_ip: string | null
        primary_ip: string | null
        secondary_ip: string | null
        orders_allowed: boolean | null
    }
}

/** `manual` is the API's word for it; `fixed` is what the user is choosing. */
type SizingMode = 'auto' | 'fixed'

const MODES: TabItem<SizingMode>[] = [
    { id: 'auto', label: 'Auto' },
    { id: 'fixed', label: 'Fixed amount' },
]

/**
 * Per-trade capital sizing.
 *
 * Two modes, and which one is active used to be implied by whether the input
 * was empty. That is a poor way to express a setting that moves real money: an
 * empty field reads as "not filled in yet" far more naturally than it reads as
 * "size from the balance automatically", and the panel could not state what was
 * actually saved because the badge was derived from the draft input rather than
 * from the stored configuration. Mode is now an explicit choice, and the header
 * badge reports the committed value — `Auto: available balance` or the rupee
 * figure — regardless of what is currently typed.
 *
 * Auto divides the available balance into equal slots rather than letting one
 * event consume all of it; see `lib/trade-sizing.ts` for the rule.
 *
 * Motion. This is a form that commits a number affecting real money, so the
 * feedback is where the motion goes:
 *
 *   - The mode pill travels between Auto and Fixed (recipe 16), as a radio
 *     group rather than a tablist: this is a value the user commits, not a view
 *     they are browsing.
 *
 *   - Each mode's detail grows and shrinks on the accordion's grid-rows
 *     mechanics (recipe 21), so switching mode resizes one region instead of
 *     cutting between two panels of different heights. The collapsed branch's
 *     input is disabled, so it cannot be reached by keyboard.
 *
 *   - The auto figures re-enter when the broker balance arrives or moves
 *     (recipe 02). They are live money read from Dhan, and marking that they
 *     changed is the point.
 *
 *   - An invalid amount shakes the field and reveals its message beneath it
 *     (recipe 12). The shake puts the feedback where the problem is, and typing
 *     cancels it so the user is not shaking at a value they are already
 *     correcting.
 *
 *   - A successful save draws a check beside the button (recipe 10), the label
 *     swaps in place while saving (recipe 04), and the panel cross-fades in
 *     from its placeholder (recipe 14).
 */
export default function TradingStatus() {
    const [tradingKeys, setTradingKeys] = useState<TradingKeys | null>(null)
    const [mode, setMode] = useState<SizingMode>('auto')
    const [tradeAmount, setTradeAmount] = useState('')
    const [status, setStatus] = useState<AmountStatus | null>(null)
    /** Available broker balance, for the auto-mode preview. */
    const [marginCapacity, setMarginCapacity] = useState<number | null>(null)
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
                setMode(loaded.trade_mode === 'manual' ? 'fixed' : 'auto')
                setTradeAmount(loaded.trade_amount ? String(loaded.trade_amount) : '')
            } catch (loadError) {
                setError(loadError instanceof Error ? loadError.message : 'Could not load trading settings.')
            } finally {
                setLoading(false)
            }
        }
        void load()
    }, [])

    /**
     * The balance is a preview of what auto mode will divide, not a
     * precondition for saving one, so it loads on its own and a broker outage
     * leaves the rest of the panel intact.
     */
    useEffect(() => {
        const loadBalance = async () => {
            try {
                const response = await fetch('/api/dhan/funds', { cache: 'no-store' })
                if (!response.ok) return
                const funds: Funds = await response.json()
                const balance = Number(funds?.availabelBalance)
                const utilized = Number(funds?.utilizedAmount)
                const startOfDay = Number(funds?.sodLimit)
                if (Number.isFinite(balance)) {
                    setMarginCapacity(Math.max(
                        balance,
                        balance + (Number.isFinite(utilized) ? Math.max(0, utilized) : 0),
                        Number.isFinite(startOfDay) ? Math.max(0, startOfDay) : 0,
                    ))
                }
            } catch {
                // Preview only. The agent re-reads the balance at execution.
            }
        }
        void loadBalance()
    }, [])

    const save = async (nextMode: SizingMode, nextAmount: number | null) => {
        try {
            setSaving(true)
            setSaved(false)
            setError(null)
            amount.clear()
            const response = await fetch('/api/ai-trading/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ trade_amount: nextMode === 'auto' ? null : nextAmount }),
            })
            const payload = await response.json().catch(() => null)
            if (!response.ok) throw new Error(payload?.error || 'Could not save your trading amount setting.')
            setStatus(payload)
            setMode(payload.trade_mode === 'manual' ? 'fixed' : 'auto')
            // Keep the typed figure when auto is saved: it is the value the user
            // will want back if they switch to a fixed cap again.
            if (payload.trade_amount) setTradeAmount(String(payload.trade_amount))
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
                        Link your Dhan account from the Portfolio screen. Once connected you can let the agent size each
                        trade from your balance, or fix an amount per trade.
                    </p>
                </PanelBody>
            </Panel>
        )
    }

    const tokenExpired = Boolean(tradingKeys?.token_expiry && new Date(tradingKeys.token_expiry) < new Date())
    const trimmed = tradeAmount.trim()
    const parsed = trimmed === '' ? null : Number(trimmed)
    const invalid = parsed !== null && (!Number.isFinite(parsed) || parsed <= 0)

    const savedMode: SizingMode = status?.trade_mode === 'manual' ? 'fixed' : 'auto'
    const savedAmount = status?.trade_amount ?? null
    const configured = Boolean(status?.configured)
    const slots = parseSlotCount(status?.auto_slots)
    const perSlot = marginCapacity === null ? null : autoSlotAmount(marginCapacity, slots)
    const fixedSlots = marginCapacity === null || parsed === null || invalid
        ? null
        : fixedSlotCount(marginCapacity, parsed)

    /**
     * A saved-but-not-eligible configuration (a stale timestamp) is fixed by
     * saving the same value again, which the status message tells the user to
     * do — so "nothing changed" must not disable the button in that state.
     */
    const needsResave = configured && status?.eligible === false
    const changed = mode === 'auto' ? savedMode !== 'auto' : parsed !== savedAmount || savedMode !== 'fixed'
    const complete = mode === 'auto' || (parsed !== null && !invalid)
    /** Nothing is stored yet, so Auto is still a change even if it is selected. */
    const pending = !configured || changed
    const canSave = complete && !invalid && !tokenExpired && (pending || needsResave)

    const changeMode = (next: SizingMode) => {
        setMode(next)
        setSaved(false)
        setError(null)
        amount.clear()
        // Offer the stored cap back rather than an empty field.
        if (next === 'fixed' && trimmed === '' && savedAmount) setTradeAmount(String(savedAmount))
    }

    const submit = () => {
        if (mode === 'fixed' && (parsed === null || invalid)) {
            setError('Enter an amount greater than zero, or switch to Auto.')
            amount.trigger()
            return
        }
        void save(mode, parsed)
    }

    return (
        <SkeletonReveal loading={loading} skeleton={<SizingSkeleton />} label="Loading trade sizing" flow>
            <Panel aria-labelledby="sizing-title">
                <PanelHeader
                    titleId="sizing-title"
                    label="Trade sizing"
                    title="Capital per trade"
                    actions={
                        // Reports what is stored, not what is typed. The saved
                        // configuration is the one the agent will trade on.
                        <Badge tone={!configured ? 'warning' : savedMode === 'auto' ? 'accent' : 'neutral'}>
                            {!configured
                                ? 'Not saved'
                                : savedMode === 'auto'
                                  ? 'Auto: available balance'
                                  : money(savedAmount || 0)}
                        </Badge>
                    }
                />
                <PanelBody className="space-y-5">
                    <p className="max-w-prose text-[12px] leading-relaxed text-ink-secondary">
                        Auto splits your available margin into {slots} equal slots, so the agent can hold {slots}{' '}
                        trades at once. Fixed derives the live-trade limit from balance divided by your margin allocation.
                        Dhan decides the live margin,
                        and exposure is capped at {status?.max_leverage || 5}x before stop-risk sizing can reduce it;
                        saving does not start a scan.
                    </p>

                    <div>
                        <p id="sizing-mode-label" className="dash-label">
                            Sizing mode
                        </p>
                        <div className="mt-2">
                            <SegmentedChoice
                                items={MODES}
                                value={mode}
                                onChange={changeMode}
                                ariaLabelledBy="sizing-mode-label"
                                disabled={tokenExpired}
                            />
                        </div>
                    </div>

                    {/* One region, two branches. Both are grid-rows disclosures
                        so the panel resizes rather than jumping between two
                        heights when the mode changes. */}
                    {/* The disclosure clips its own overflow, which would cut
                        the field's focus ring and the error shake's travel. The
                        inner padding gives both room; the negative margin puts
                        the content back on the panel's own alignment. */}
                    <div className="-mx-3 -my-2">
                        <DisclosurePanel
                            open={mode === 'auto'}
                            ariaLabel="Automatic sizing"
                            panelClassName="px-3 py-2"
                        >
                            <div className="rounded-lg border border-line bg-white/[0.02] p-3.5">
                                <dl className="grid grid-cols-3 gap-3">
                                    <SlotFigure label="Margin capacity" value={marginCapacity === null ? '—' : money(marginCapacity)} />
                                    <SlotFigure label="Margin per trade" value={perSlot === null ? '—' : money(perSlot)} />
                                    <SlotFigure label="Slots" value={String(slots)} plain />
                                </dl>
                                <p className="mt-3 text-[11px] leading-relaxed text-ink-tertiary">
                                    {perSlot === null
                                        ? `Your balance could not be read just now. The split still happens at execution, against whatever is available then.`
                                        : `Up to ${money(perSlot)} margin per trade. Dhan margin, the leverage cap, and stop risk determine the final quantity.`}
                                </p>
                            </div>
                        </DisclosurePanel>

                        <DisclosurePanel
                            open={mode === 'fixed'}
                            ariaLabel="Fixed amount"
                            panelClassName="px-3 py-2"
                        >
                            <div className={amount.wrapClass}>
                                <label htmlFor="trade-amount" className="dash-label">
                                    Margin per trade
                                </label>
                                <div className="mt-2 flex items-center gap-2">
                                    {/* The bordered wrapper is the shaking
                                        element, not the input: the border is
                                        what changes tone, and translating the
                                        input alone would slide the currency
                                        glyph out of its own field. */}
                                    <div
                                        ref={amount.fieldRef}
                                        className={`${amount.fieldClass} relative flex-1 rounded-lg`}
                                    >
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
                                                // Correcting the value clears
                                                // the error immediately rather
                                                // than waiting out the revert
                                                // timer.
                                                amount.clear()
                                                setError(null)
                                            }}
                                            placeholder="Margin per trade"
                                            // A collapsed panel still holds
                                            // focusable children, so the field
                                            // is disabled out of Fixed mode.
                                            disabled={tokenExpired || mode !== 'fixed'}
                                            aria-label="Trading amount in rupees"
                                            aria-invalid={invalid || amount.errored}
                                            aria-describedby="trade-amount-hint trade-amount-error"
                                            className="dash-input dash-input-currency border-0 bg-transparent focus:shadow-none"
                                        />
                                    </div>
                                </div>

                                <ErrorMessage id="trade-amount-error">{error}</ErrorMessage>

                                <p id="trade-amount-hint" className="mt-1 text-[10px] text-ink-tertiary">
                                    {parsed === null || invalid
                                        ? 'The maximum broker margin one trade may use.'
                                        : `Each trade may use up to ${money(parsed)} margin. Current capacity: ${fixedSlots ?? 0} concurrent trades before leverage and stop-risk limits.`}
                                </p>
                            </div>
                        </DisclosurePanel>
                    </div>

                    <div className="flex items-center gap-2">
                        <Button variant="solid" onClick={submit} disabled={saving || !canSave} swapLabel>
                            {saving ? 'Saving' : configured ? 'Update' : 'Save'}
                        </Button>
                        {/* Persistent, not a toast: the confirmation belongs
                            next to the control that produced it, and it clears
                            on the next edit. */}
                        {saved && <SuccessCheck size={16} className="text-positive" />}
                        {pending && !saving && !saved && (
                            <span className="text-[10px] text-ink-tertiary">Not saved yet</span>
                        )}
                    </div>

                    {tokenExpired ? (
                        <Notice tone="danger">
                            Your broker token has expired. Order dispatch is paused for your account while market
                            monitoring continues. Reconnect Dhan from the Portfolio screen to resume.
                        </Notice>
                    ) : (
                        <Notice tone={status?.eligible ? 'neutral' : 'warning'}>
                            {status?.message || 'Choose Auto to size from your balance, or Fixed to cap each trade.'}
                        </Notice>
                    )}
                    {status?.order_placement && !status.order_placement.allowed && (
                        <Notice tone="danger">
                            Dhan order placement is paused, so AI agents will not run. The detected IP is{' '}
                            <span className="font-mono">
                                {status.order_placement.detected_ip || 'unavailable'}
                            </span>
                            . The next automatic verification is{' '}
                            <span className="font-mono">
                                {status.order_placement.next_verification_at_utc
                                    ? formatDateTime(status.order_placement.next_verification_at_utc)
                                    : 'pending'}
                            </span>
                            .
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

/**
 * One figure in the auto-mode split.
 *
 * `plain` opts out of the pop-in for values that are configuration rather than
 * money: the slot count does not move on its own, so animating it would imply
 * a change that never happens.
 */
function SlotFigure({ label, value, plain }: { label: string; value: string; plain?: boolean }) {
    return (
        <div>
            <dt className="dash-label">{label}</dt>
            <dd className="mt-1 font-mono text-[13px] tabular-nums text-ink-primary">
                {plain ? value : <NumberFlow value={value} />}
            </dd>
        </div>
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
                <Skeleton className="h-9 w-48" delay={80} />
                <Skeleton className="h-16 w-full" delay={120} />
                <Skeleton className="h-9 w-24" delay={160} />
            </div>
        </Panel>
    )
}
