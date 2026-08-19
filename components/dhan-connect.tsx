'use client'

import { FormEvent, useEffect, useRef, useState } from 'react'
import { createClient } from '@/lib/supabase/client'
import { cn } from '@/lib/cn'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Close, Link as LinkIcon } from '@/components/ui/icons'
import { ClearableInput } from '@/components/motion/clearable-input'
import { ErrorMessage, useErrorShake } from '@/components/motion/error-field'
import { LearnMoreChevron } from '@/components/motion/learn-more'
import { Modal } from '@/components/motion/modal'
import { Morph } from '@/components/motion/morph'
import { SkeletonReveal } from '@/components/motion/skeleton-reveal'
import { StatusDot } from '@/components/ui/badge'

type Connection = {
    dhan_client_id: string
    token_expiry: string | null
}

const LOGO_URL = 'https://dhan.co/_next/static/media/Dhanlogo.8a85768d.svg'

/**
 * Broker connection control.
 *
 * One pill that reports connection state and expands into the client-ID form.
 *
 * Motion. This replaces a `framer-motion` `layout` + `AnimatePresence` stack
 * with three recipes, each matched to what the interaction actually is:
 *
 *   - Connecting uses the trigger-to-surface morph (recipe 20). The trigger and
 *     the form are the *same element* — the pill grows in place into the field —
 *     which is precisely the case the morph exists for and precisely the case a
 *     dropdown does not fit: a dropdown implies a separate popover appearing
 *     beside a button that stays put. Opening carries the bouncier curve;
 *     closing does not.
 *
 *   - Disconnecting is a modal (recipe 06), not a third state of the pill. It
 *     destroys a credential and cannot be undone, so it should block and demand
 *     a response rather than being a panel the user can click past. It also gets
 *     focus containment and Escape-to-dismiss, which the previous inline
 *     confirmation had neither of.
 *
 *   - The client-ID field uses the input-clear dissolve (recipe 13).
 *
 * Failures shake the field (recipe 12) rather than printing a message in the
 * corner, and the initial connection check cross-fades from its placeholder
 * (recipe 14) rather than swapping a pulsing block for the real control.
 */
export default function DhanConnect() {
    const [clientId, setClientId] = useState('')
    const [connection, setConnection] = useState<Connection | null>(null)
    const [connectOpen, setConnectOpen] = useState(false)
    const [disconnectOpen, setDisconnectOpen] = useState(false)
    const [isLoading, setIsLoading] = useState(false)
    const [isChecking, setIsChecking] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const field = useErrorShake<HTMLDivElement>()
    const inputHost = useRef<HTMLDivElement | null>(null)

    useEffect(() => {
        const loadConnection = async () => {
            const supabase = createClient()
            const {
                data: { user },
            } = await supabase.auth.getUser()
            if (!user) {
                setIsChecking(false)
                return
            }

            const { data } = await supabase
                .from('user_trading_keys')
                .select('dhan_client_id, token_expiry')
                .eq('user_id', user.id)
                .maybeSingle()

            if (data) setConnection(data)
            setIsChecking(false)
        }

        void loadConnection()
    }, [])

    // Focus the field once the morph has finished growing. Focusing before the
    // box has resized makes the browser scroll to a control that is still
    // mid-transition.
    useEffect(() => {
        if (!connectOpen) return
        const timer = window.setTimeout(
            () => inputHost.current?.querySelector('input')?.focus({ preventScroll: true }),
            220,
        )
        return () => window.clearTimeout(timer)
    }, [connectOpen])

    const openConnect = () => {
        setError(null)
        field.clear()
        setClientId(connection?.dhan_client_id || '')
        setConnectOpen(true)
    }

    const closeConnect = () => {
        if (isLoading) return
        setError(null)
        field.clear()
        setConnectOpen(false)
    }

    const handleConnect = async (event: FormEvent) => {
        event.preventDefault()
        const trimmed = clientId.trim()
        if (!trimmed) {
            setError('Enter your Dhan client ID.')
            field.trigger()
            return
        }

        setIsLoading(true)
        setError(null)

        try {
            const response = await fetch('/api/dhan/auth', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ dhanClientId: trimmed }),
            })
            const data = await response.json()
            if (!response.ok) throw new Error(data.error || 'Failed to initiate connection')
            window.location.href = data.url
        } catch (connectError) {
            setError(connectError instanceof Error ? connectError.message : 'Unable to connect right now')
            field.trigger()
            setIsLoading(false)
        }
    }

    const handleDisconnect = async () => {
        setIsLoading(true)
        setError(null)

        try {
            const response = await fetch('/api/dhan/connection', { method: 'DELETE' })
            const data = await response.json().catch(() => null)
            if (!response.ok) throw new Error(data?.error || 'Unable to disconnect Dhan')

            setConnection(null)
            setClientId('')
            setDisconnectOpen(false)
            window.dispatchEvent(new CustomEvent('dhan-connection-change', { detail: { connected: false } }))
        } catch (disconnectError) {
            setError(disconnectError instanceof Error ? disconnectError.message : 'Unable to disconnect Dhan')
        } finally {
            setIsLoading(false)
        }
    }

    const tokenExpired = connection?.token_expiry ? new Date(connection.token_expiry) < new Date() : false

    return (
        <SkeletonReveal
            loading={isChecking}
            skeleton={<Skeleton className="h-12 w-full rounded-2xl sm:w-[320px]" />}
            label="Checking broker connection"
            flow
            className="w-full sm:w-[320px]"
        >
            {/* The width is declared here, on an element in normal flow.
                `Morph` applies its size inline, but both of its layers are
                absolutely positioned, so the pill has no in-flow content to
                shrink-wrap: anything that resolves its width to auto collapses
                it to zero. An auto-width utility carrying `!important` used to
                sit on the Morph, which outranks a plain inline style, so the
                control was 0px wide at every breakpoint above mobile. Keep
                width off the Morph. */}
            <div className="relative w-full sm:w-[320px]">
                <Morph
                    open={connectOpen}
                    closedSize={{ width: '100%', height: 48 }}
                    openSize={{ width: '100%', height: 48 }}
                    className={cn(
                        'border shadow-[0_18px_50px_-30px_rgba(0,0,0,0.9)]',
                        connection && !tokenExpired
                            ? 'border-positive/20 bg-[#0D1510]'
                            : tokenExpired
                              ? 'border-warning/25 bg-[#151206]'
                              : 'border-line bg-panel',
                    )}
                    label="Dhan broker connection"
                    resting={
                        // `min-width` here could only make this layer overflow
                        // its own frame; the pill's width is set on the wrapper.
                        <div className="flex h-full items-stretch">
                            <button
                                type="button"
                                onClick={openConnect}
                                className="group flex min-w-0 flex-1 items-center gap-3 px-4 text-left outline-none"
                                aria-label={connection ? 'Re-enter your Dhan client ID' : 'Connect to Dhan'}
                            >
                                {/* Third-party asset of unknown dimensions served
                                    from Dhan's CDN; next/image would add nothing. */}
                                {/* eslint-disable-next-line @next/next/no-img-element */}
                                <img
                                    src={LOGO_URL}
                                    alt=""
                                    className="h-[19px] w-auto shrink-0 opacity-90 transition-transform duration-[250ms] ease-[cubic-bezier(0.22,1,0.36,1)] group-hover:scale-[1.04]"
                                />
                                {connection ? (
                                    <>
                                        <StatusDot tone={tokenExpired ? 'warning' : 'positive'} pulse={!tokenExpired} />
                                        <span className="min-w-0 leading-tight">
                                            <span className="block truncate text-[11px] font-medium text-ink-primary">
                                                {tokenExpired ? 'Session expired' : 'Dhan connected'}
                                            </span>
                                            <span className="block font-mono text-[8px] tracking-wide text-ink-tertiary">
                                                ID {connection.dhan_client_id}
                                            </span>
                                        </span>
                                    </>
                                ) : (
                                    <>
                                        <span className="text-[12px] font-medium text-ink-primary">
                                            Connect to Dhan
                                        </span>
                                        <span className="ml-auto text-ink-tertiary">
                                            <LearnMoreChevron size={15} />
                                        </span>
                                    </>
                                )}
                            </button>

                            {connection && (
                                <button
                                    type="button"
                                    onClick={() => {
                                        setError(null)
                                        setDisconnectOpen(true)
                                    }}
                                    className="flex flex-shrink-0 items-center border-l border-white/[0.07] px-3.5 text-[10px] text-ink-tertiary transition-colors duration-[250ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:bg-white/[0.03] hover:text-negative"
                                    aria-label="Log out of Dhan"
                                >
                                    Logout
                                </button>
                            )}
                        </div>
                    }
                    expanded={
                        <form onSubmit={handleConnect} className="flex h-full items-center gap-1.5 p-1.5">
                            <span className="grid h-9 w-9 flex-shrink-0 place-items-center">
                                {/* eslint-disable-next-line @next/next/no-img-element */}
                                <img src={LOGO_URL} alt="" className="h-[18px] w-auto opacity-80" />
                            </span>
                            <div ref={inputHost} className="min-w-0 flex-1">
                                <label htmlFor="dhan-client-id" className="sr-only">
                                    Dhan Client ID
                                </label>
                                <div ref={field.fieldRef} className={cn(field.fieldClass, 'rounded-xl')}>
                                    <ClearableInput
                                        id="dhan-client-id"
                                        value={clientId}
                                        onValueChange={(next) => {
                                            setClientId(next)
                                            field.clear()
                                            setError(null)
                                        }}
                                        placeholder="Enter client ID"
                                        inputMode="numeric"
                                        autoComplete="off"
                                        disabled={isLoading}
                                        aria-describedby="dhan-connect-error"
                                        className="border-0 bg-transparent"
                                    />
                                </div>
                            </div>
                            <Button
                                type="submit"
                                variant="solid"
                                size="sm"
                                disabled={isLoading || !clientId.trim()}
                                className="h-9 flex-shrink-0 rounded-xl px-4 !bg-positive !text-[#061109] hover:!bg-[#44df84]"
                                swapLabel
                            >
                                {isLoading ? 'Connecting' : connection ? 'Reconnect' : 'Connect'}
                            </Button>
                            <button
                                type="button"
                                onClick={closeConnect}
                                className="t-press grid h-9 w-8 flex-shrink-0 place-items-center rounded-lg text-ink-tertiary transition-colors duration-[250ms] hover:bg-white/[0.04] hover:text-ink-primary"
                                aria-label="Cancel"
                            >
                                <Close size={14} />
                            </button>
                        </form>
                    }
                />

                <div className={field.wrapClass}>
                    <ErrorMessage id="dhan-connect-error" className="absolute right-0 top-full text-right text-[10px]">
                        {error}
                    </ErrorMessage>
                </div>
            </div>

            <Modal
                open={disconnectOpen}
                onClose={() => !isLoading && setDisconnectOpen(false)}
                labelledBy="dhan-disconnect-title"
                describedBy="dhan-disconnect-detail"
            >
                <div className="p-5">
                    <span className="mb-4 grid h-9 w-9 place-items-center rounded-full border border-negative/25 bg-negative/[0.08] text-negative">
                        <LinkIcon size={16} />
                    </span>
                    <h2
                        id="dhan-disconnect-title"
                        className="text-[15px] font-medium tracking-[-0.02em] text-ink-primary"
                    >
                        Log out of Dhan?
                    </h2>
                    <p id="dhan-disconnect-detail" className="mt-2 text-[12px] leading-relaxed text-ink-secondary">
                        Your broker token will be removed and order dispatch will stop. Your portfolio figures will
                        clear until you reconnect.
                    </p>
                    {error && <p className="mt-3 text-[11px] text-negative">{error}</p>}
                    <div className="mt-5 flex justify-end gap-2">
                        <Button onClick={() => setDisconnectOpen(false)} disabled={isLoading}>
                            Cancel
                        </Button>
                        <Button
                            onClick={handleDisconnect}
                            disabled={isLoading}
                            className="!bg-negative !text-[#180606] hover:!bg-negative/90"
                            swapLabel
                        >
                            {isLoading ? 'Logging out' : 'Log out'}
                        </Button>
                    </div>
                </div>
            </Modal>
        </SkeletonReveal>
    )
}
