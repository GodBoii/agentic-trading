'use client'

import Link from 'next/link'
import { useEffect, useRef, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Notice } from '@/components/ui/notice'
import { Panel } from '@/components/ui/panel'
import { Skeleton } from '@/components/ui/skeleton'
import { ChevronRight, Scales } from '@/components/ui/icons'
import { SegmentedChoice, type TabItem } from '@/components/ui/tabs'
import { AccordionChevron, AccordionShell, DisclosurePanel } from '@/components/motion/accordion'
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
 * Per-trade capital sizing, as one row that opens.
 *
 * This setting used to occupy a whole view of its own, reached through a tab on
 * the Agent page, and inside that view it was a panel containing a paragraph,
 * a mode selector, a bordered card inside a padded well holding three figures,
 * two notices and a footer. A screenful of chrome around a single number.
 *
 * Two things were wrong with that, and they compound. A tab implies a peer view
 * — something you go and look at — when this is a setting that belongs beside
 * the thing it governs; putting it behind a tab meant the run and the limit the
 * run trades under were never on screen together. And the committed value was
 * only visible after navigating to it, so the answer to "how much can the agent
 * spend right now" cost a click.
 *
 * So: the summary line is always readable, and the editor grows out of it in
 * place. One container, no nested cards, figures on one line of accounting
 * rather than in a grid of boxes.
 *
 * Behaviour is unchanged. Auto divides the available balance into equal slots
 * rather than letting one event consume all of it (see `lib/trade-sizing.ts`);
 * Fixed caps the margin one trade may use. Mode is an explicit choice rather
 * than being implied by whether the input is empty — an empty field reads as
 * "not filled in yet" far more naturally than it reads as "size from the
 * balance automatically", which is not a thing to be ambiguous about when it
 * moves real money. The badge reports what is *stored*, never what is typed.
 *
 * Motion, in the order the user meets it:
 *
 *   - The editor grows on the accordion's grid-rows mechanics (recipe 21), so
 *     the page reflows once, smoothly, rather than the run below it jumping.
 *   - The mode pill travels between Auto and Fixed (recipe 16), as a radio
 *     group: this is a value the user commits, not a view they browse.
 *   - The broker figures re-enter when the balance arrives or moves (recipe 02).
 *     They are live money read from Dhan, and marking that they changed is the
 *     entire point of showing them.
 *   - An invalid amount shakes the field and reveals its message beneath it
 *     (recipe 12). Typing cancels it, so the user is never shaking at a value
 *     they are already correcting.
 *   - A successful save draws a check beside the button (recipe 10) and the
 *     label swaps in place while saving (recipe 04).
 */
export function CapitalControl() {
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
    const [expanded, setExpanded] = useState(false)
    const amount = useErrorShake<HTMLDivElement>()
    /** Guards the one-time auto-open, so a later save cannot reopen the editor. */
    const promptedOnce = useRef(false)

    useEffect(() => {
        const load = async () => {
            try {
                const connectionResponse = await fetch('/api/dhan/connection', { cache: 'no-store' })
                const connection = await connectionResponse.json()
                if (!connectionResponse.ok) throw new Error(connection.error || 'Could not check Dhan connection.')
                setTradingKeys(connection.connected ? { token_expiry: connection.tokenExpiresAt } : null)

                const response = await fetch('/api/ai-trading/config', { cache: 'no-store' })
                if (!response.ok) throw new Error('Could not load your trading amount setting.')
                const loaded: AmountStatus = await response.json()
                setStatus(loaded)
                setMode(loaded.trade_mode === 'manual' ? 'fixed' : 'auto')
                setTradeAmount(loaded.trade_amount ? String(loaded.trade_amount) : '')

                // Nothing stored yet: open the editor once, because a collapsed
                // row saying "not set" is a instruction with no control attached.
                if (!loaded.configured && !promptedOnce.current) {
                    promptedOnce.current = true
                    setExpanded(true)
                }
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
     * leaves the rest of the control intact.
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
                    setMarginCapacity(
                        Math.max(
                            balance,
                            balance + (Number.isFinite(utilized) ? Math.max(0, utilized) : 0),
                            Number.isFinite(startOfDay) ? Math.max(0, startOfDay) : 0,
                        ),
                    )
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
        // A dead end here would be the worst version of this state: the fix is
        // on another screen, so the row links there rather than describing it.
        return (
            <Panel>
                <div className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
                    <span className="flex min-w-0 items-center gap-3">
                        <Scales size={16} className="flex-shrink-0 text-ink-tertiary" />
                        <span className="min-w-0">
                            <span className="block text-[12.5px] font-medium text-ink-primary">
                                Capital per trade
                            </span>
                            <span className="mt-0.5 block text-[11px] leading-relaxed text-ink-tertiary">
                                Connect Dhan to set how much margin one trade may use.
                            </span>
                        </span>
                    </span>
                    <Link
                        href="/dashboard"
                        className="t-press inline-flex h-8 flex-shrink-0 items-center gap-1 self-start rounded-lg border border-line px-3 text-[11px] font-medium text-ink-secondary transition-[color,background-color,border-color] duration-fast ease-smooth hover:border-line-strong hover:bg-surface-hover hover:text-ink-primary sm:self-auto"
                    >
                        Connect on Portfolio
                        <ChevronRight size={13} />
                    </Link>
                </div>
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
    const fixedSlots =
        marginCapacity === null || parsed === null || invalid ? null : fixedSlotCount(marginCapacity, parsed)
    const savedFixedSlots =
        marginCapacity === null || savedAmount === null ? null : fixedSlotCount(marginCapacity, savedAmount)

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

    /**
     * The one line that has to be true at a glance. It reports the *stored*
     * configuration, because that is what the agent will trade on — not
     * whatever is currently in the input.
     */
    const summary = !configured
        ? 'Not set. The agent will not place an order until this is saved.'
        : savedMode === 'auto'
          ? perSlot === null
              ? `Automatic. Your available margin is split into ${slots} equal slots at execution.`
              : `Automatic. Up to ${money(perSlot)} margin per trade, across ${slots} slots.`
          : savedFixedSlots === null
            ? `Fixed at ${money(savedAmount || 0)} margin per trade.`
            : `Fixed at ${money(savedAmount || 0)} per trade, funding ${savedFixedSlots} concurrent ${
                  savedFixedSlots === 1 ? 'position' : 'positions'
              }.`

    return (
        <SkeletonReveal loading={loading} skeleton={<CapitalSkeleton />} label="Loading capital settings" flow>
            <div className="space-y-3">
                <Panel aria-labelledby="capital-title">
                    <AccordionShell
                        open={expanded}
                        onToggle={() => setExpanded((current) => !current)}
                        headerClassName="px-4 py-3.5 sm:px-5"
                        panelClassName="border-t border-line px-4 py-4 sm:px-5"
                        header={
                            <>
                                <Scales
                                    size={17}
                                    className={
                                        configured ? 'flex-shrink-0 text-ink-secondary' : 'flex-shrink-0 text-warning'
                                    }
                                />
                                <span className="min-w-0 flex-1">
                                    <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                                        <span
                                            id="capital-title"
                                            className="text-[12.5px] font-medium tracking-[-0.015em] text-ink-primary"
                                        >
                                            Capital per trade
                                        </span>
                                        {/* Reports what is stored, not what is
                                            typed. The saved configuration is
                                            the one the agent will trade on. */}
                                        <Badge
                                            size="sm"
                                            tone={
                                                !configured
                                                    ? 'warning'
                                                    : savedMode === 'auto'
                                                      ? 'accent'
                                                      : 'neutral'
                                            }
                                        >
                                            {!configured ? 'Not saved' : savedMode === 'auto' ? 'Auto' : 'Fixed'}
                                        </Badge>
                                    </span>
                                    <span className="mt-1 block text-[11px] leading-relaxed text-ink-tertiary">
                                        {summary}
                                    </span>
                                </span>
                                <span className="flex flex-shrink-0 items-center gap-1.5 text-[10px] uppercase tracking-[0.12em] text-ink-tertiary">
                                    <span className="hidden sm:inline">{expanded ? 'Close' : 'Adjust'}</span>
                                    <AccordionChevron size={14} />
                                </span>
                            </>
                        }
                    >
                        <div className="space-y-4">
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
                                        // A collapsed grid track still holds
                                        // focusable children, so every control
                                        // in here is disabled when closed.
                                        disabled={tokenExpired || !expanded}
                                    />
                                </div>
                            </div>

                            {/*
                             * The amount field grows and shrinks rather than
                             * appearing between frames when the mode changes.
                             * Rendering it conditionally inside an already-open
                             * accordion would resize the outer panel in a single
                             * frame, which reads as the page jumping under the
                             * pointer that just changed the mode.
                             *
                             * The negative margin pays for the disclosure's own
                             * `overflow: hidden`: without inner padding it clips
                             * the field's focus ring and the error shake's
                             * travel, and the offset puts the content back on
                             * the panel's alignment.
                             */}
                            <div className="-mx-2 -my-1.5">
                                <DisclosurePanel
                                    open={mode === 'fixed'}
                                    ariaLabel="Fixed amount"
                                    panelClassName="px-2 py-1.5"
                                >
                                    <div className={`${amount.wrapClass} max-w-[260px]`}>
                                        <label htmlFor="trade-amount" className="dash-label">
                                            Margin per trade
                                        </label>
                                        {/* The bordered wrapper is the shaking
                                            element, not the input: the border is
                                            what changes tone, and translating
                                            the input alone would slide the
                                            currency glyph out of its own
                                            field. */}
                                        <div
                                            ref={amount.fieldRef}
                                            className={`${amount.fieldClass} relative mt-2 rounded-lg border border-line bg-surface`}
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
                                                placeholder="0.00"
                                                disabled={tokenExpired || !expanded || mode !== 'fixed'}
                                                aria-label="Margin per trade in rupees"
                                                aria-invalid={invalid || amount.errored}
                                                aria-describedby="trade-amount-hint trade-amount-error"
                                                className="dash-input dash-input-currency border-0 bg-transparent focus:shadow-none"
                                            />
                                        </div>
                                        <ErrorMessage id="trade-amount-error">
                                            {mode === 'fixed' ? error : null}
                                        </ErrorMessage>
                                    </div>
                                </DisclosurePanel>
                            </div>

                            {/* One line of accounting rather than three boxes.
                                The figures are the same in both modes; only
                                which one the user controls changes. */}
                            <dl className="figure-row border-t border-line pt-3.5">
                                <div>
                                    <dt>Margin capacity</dt>
                                    <dd>
                                        {marginCapacity === null ? '—' : <NumberFlow value={money(marginCapacity)} />}
                                    </dd>
                                </div>
                                <div>
                                    <dt>Per trade</dt>
                                    <dd>
                                        {mode === 'auto' ? (
                                            perSlot === null ? (
                                                '—'
                                            ) : (
                                                <NumberFlow value={money(perSlot)} />
                                            )
                                        ) : parsed === null || invalid ? (
                                            '—'
                                        ) : (
                                            money(parsed)
                                        )}
                                    </dd>
                                </div>
                                <div>
                                    <dt>Concurrent positions</dt>
                                    <dd>{mode === 'auto' ? slots : (fixedSlots ?? '—')}</dd>
                                </div>
                                <div>
                                    <dt>Leverage cap</dt>
                                    <dd>{status?.max_leverage || 5}x</dd>
                                </div>
                            </dl>

                            <p id="trade-amount-hint" className="max-w-prose text-[11px] leading-relaxed text-ink-tertiary">
                                {mode === 'auto'
                                    ? `Auto splits the margin available at execution into ${slots} equal slots, so a position taken in the morning cannot starve the ones the agent wants later.`
                                    : 'Fixed caps the broker margin any single trade may use. The concurrent figure is what your current balance supports.'}{' '}
                                Dhan decides the live margin either way, exposure is capped at{' '}
                                {status?.max_leverage || 5}x, and stop-risk sizing can reduce the quantity further.
                                Saving does not start a scan.
                            </p>

                            <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                                <Button
                                    variant="solid"
                                    onClick={submit}
                                    disabled={saving || !canSave || !expanded}
                                    swapLabel
                                >
                                    {saving ? 'Saving' : configured ? 'Update' : 'Save'}
                                </Button>
                                {/* Persistent, not a toast: the confirmation
                                    belongs next to the control that produced
                                    it, and it clears on the next edit. */}
                                {saved && <SuccessCheck size={16} className="text-positive" />}
                                {pending && !saving && !saved && (
                                    <span className="text-[10px] text-ink-tertiary">Not saved yet</span>
                                )}
                                {status?.amount_updated_at_utc && !pending && (
                                    <span className="text-[10px] text-ink-tertiary">
                                        Last changed{' '}
                                        <span className="font-mono">
                                            {formatDateTime(status.amount_updated_at_utc)}
                                        </span>
                                    </span>
                                )}
                                {/* In Auto mode there is no field to put a
                                   failure beside, so a failed save reports
                                   itself next to the control that caused it.
                                   Previously the message was only rendered
                                   inside the Fixed branch, which meant an Auto
                                   save that failed said nothing at all. */}
                                {mode === 'auto' && error && (
                                    <span role="alert" className="text-[11px] text-negative">
                                        {error}
                                    </span>
                                )}
                            </div>
                        </div>
                    </AccordionShell>
                </Panel>

                {/*
                 * Notices sit outside the collapsible region on purpose. Each of
                 * these describes a condition that stops the agent trading, and
                 * hiding that behind a disclosure would mean the run below looks
                 * healthy while nothing can actually execute.
                 */}
                {tokenExpired && (
                    <Notice tone="danger">
                        Your broker token has expired. Order dispatch is paused for your account while market
                        monitoring continues. Reconnect Dhan from the Portfolio screen to resume.
                    </Notice>
                )}
                {!tokenExpired && status && !status.eligible && (
                    <Notice tone="warning">{status.message}</Notice>
                )}
                {status?.order_placement && !status.order_placement.allowed && (
                    <Notice tone="danger">
                        Dhan order placement is paused, so AI agents will not run. The detected IP is{' '}
                        <span className="font-mono">{status.order_placement.detected_ip || 'unavailable'}</span>. The
                        next automatic verification is{' '}
                        <span className="font-mono">
                            {status.order_placement.next_verification_at_utc
                                ? formatDateTime(status.order_placement.next_verification_at_utc)
                                : 'pending'}
                        </span>
                        .
                    </Notice>
                )}
            </div>
        </SkeletonReveal>
    )
}

/** Shaped like the collapsed row, so nothing shifts when the setting arrives. */
function CapitalSkeleton() {
    return (
        <Panel>
            <div className="flex items-center gap-3 px-4 py-3.5 sm:px-5">
                <Skeleton className="h-4 w-4 rounded" />
                <div className="min-w-0 flex-1">
                    <Skeleton className="h-3 w-40" />
                    <Skeleton className="mt-2 h-2.5 w-64 max-w-full" delay={40} />
                </div>
                <Skeleton className="h-3 w-12" delay={80} />
            </div>
        </Panel>
    )
}

export default CapitalControl
