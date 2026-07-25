'use client'

import { FormEvent, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { createClient } from '@/lib/supabase/client'

type Connection = {
    dhan_client_id: string
    token_expiry: string | null
}

type View = 'summary' | 'connect' | 'disconnect'

const logoUrl = 'https://dhan.co/_next/static/media/Dhanlogo.8a85768d.svg'
const spring = { type: 'spring', stiffness: 430, damping: 38, mass: 0.8 } as const

export default function DhanConnect() {
    const [clientId, setClientId] = useState('')
    const [connection, setConnection] = useState<Connection | null>(null)
    const [view, setView] = useState<View>('summary')
    const [isLoading, setIsLoading] = useState(false)
    const [isChecking, setIsChecking] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const inputRef = useRef<HTMLInputElement>(null)

    useEffect(() => {
        const loadConnection = async () => {
            const supabase = createClient()
            const { data: { user } } = await supabase.auth.getUser()
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

        loadConnection()
    }, [])

    useEffect(() => {
        if (view === 'connect') {
            const timer = window.setTimeout(() => inputRef.current?.focus(), 180)
            return () => window.clearTimeout(timer)
        }
    }, [view])

    const openConnect = () => {
        setError(null)
        setClientId(connection?.dhan_client_id || '')
        setView('connect')
    }

    const returnToSummary = () => {
        if (isLoading) return
        setError(null)
        setView('summary')
    }

    const handleConnect = async (event: FormEvent) => {
        event.preventDefault()
        setIsLoading(true)
        setError(null)

        try {
            const response = await fetch('/api/dhan/auth', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ dhanClientId: clientId.trim() }),
            })
            const data = await response.json()
            if (!response.ok) throw new Error(data.error || 'Failed to initiate connection')
            window.location.href = data.url
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Unable to connect right now')
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
            setView('summary')
            window.dispatchEvent(new CustomEvent('dhan-connection-change', { detail: { connected: false } }))
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Unable to disconnect Dhan')
        } finally {
            setIsLoading(false)
        }
    }

    const tokenExpired = connection?.token_expiry
        ? new Date(connection.token_expiry) < new Date()
        : false

    if (isChecking) {
        return <div className="h-12 w-48 animate-pulse rounded-2xl bg-white/[0.04]" />
    }

    return (
        <motion.div
            layout
            transition={spring}
            className="relative w-full sm:w-auto"
        >
            <motion.div
                layout
                transition={spring}
                className={`relative overflow-hidden rounded-2xl border shadow-[0_18px_50px_-30px_rgba(0,0,0,0.9)] ${
                    connection
                        ? 'border-[#37d67a]/20 bg-[#0d1510]'
                        : 'border-[var(--dash-border)] bg-[#0e0e11]'
                }`}
            >
                <AnimatePresence mode="popLayout" initial={false}>
                    {view === 'summary' && (
                        <motion.div
                            key="summary"
                            layout
                            initial={{ opacity: 0, filter: 'blur(5px)', scale: 0.98 }}
                            animate={{ opacity: 1, filter: 'blur(0px)', scale: 1 }}
                            exit={{ opacity: 0, filter: 'blur(5px)', scale: 0.98 }}
                            transition={{ duration: 0.2 }}
                            className="flex h-12 min-w-[210px] items-stretch"
                        >
                            <button
                                type="button"
                                onClick={openConnect}
                                className="group flex min-w-0 flex-1 items-center gap-3 px-4 text-left outline-none"
                                aria-label={connection ? 'Enter a Dhan Client ID' : 'Connect to Dhan'}
                            >
                                <img
                                    src={logoUrl}
                                    alt=""
                                    className="h-[19px] w-auto shrink-0 opacity-90 transition-transform duration-500 group-hover:scale-[1.04]"
                                />
                                {connection ? (
                                    <>
                                        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${tokenExpired ? 'bg-[var(--dash-warning)]' : 'bg-[#37d67a]'}`} />
                                        <span className="min-w-0 leading-tight">
                                            <span className="block truncate text-[11px] font-medium text-[var(--dash-text)]">
                                                {tokenExpired ? 'Session expired' : 'Dhan connected'}
                                            </span>
                                            <span className="block font-mono text-[8px] tracking-wide text-[var(--dash-text-muted)]">
                                                ID {connection.dhan_client_id}
                                            </span>
                                        </span>
                                    </>
                                ) : (
                                    <>
                                        <span className="text-[12px] font-medium text-[var(--dash-text)]">Connect to Dhan</span>
                                        <span aria-hidden className="ml-auto text-[15px] text-[var(--dash-text-muted)] transition-transform duration-300 group-hover:translate-x-0.5">→</span>
                                    </>
                                )}
                            </button>

                            {connection && (
                                <button
                                    type="button"
                                    onClick={() => {
                                        setError(null)
                                        setView('disconnect')
                                    }}
                                    className="group relative flex items-center border-l border-white/[0.07] px-3.5 text-[10px] text-[var(--dash-text-muted)] transition-colors hover:bg-white/[0.025] hover:text-[var(--dash-negative)]"
                                    aria-label="Log out of Dhan"
                                >
                                    Logout
                                </button>
                            )}
                        </motion.div>
                    )}

                    {view === 'connect' && (
                        <motion.form
                            key="connect"
                            layout
                            onSubmit={handleConnect}
                            initial={{ opacity: 0, filter: 'blur(5px)' }}
                            animate={{ opacity: 1, filter: 'blur(0px)' }}
                            exit={{ opacity: 0, filter: 'blur(5px)' }}
                            transition={{ duration: 0.22 }}
                            className="flex min-h-12 w-full items-center p-1.5 sm:w-[440px]"
                        >
                            <div className="flex min-w-0 flex-1 items-center gap-2.5 px-2">
                                <img src={logoUrl} alt="" className="h-[18px] w-auto shrink-0 opacity-80" />
                                <label htmlFor="dhan-client-id" className="sr-only">Dhan Client ID</label>
                                <input
                                    ref={inputRef}
                                    id="dhan-client-id"
                                    inputMode="numeric"
                                    autoComplete="off"
                                    value={clientId}
                                    onChange={(event) => setClientId(event.target.value)}
                                    placeholder="Enter client ID"
                                    disabled={isLoading}
                                    className="h-9 min-w-0 flex-1 border-0 bg-transparent font-mono text-[12px] text-[var(--dash-text)] outline-none placeholder:text-[var(--dash-text-muted)]"
                                    aria-describedby={error ? 'dhan-connect-error' : undefined}
                                />
                            </div>
                            <button
                                type="submit"
                                disabled={isLoading || !clientId.trim()}
                                className="h-9 shrink-0 rounded-xl bg-[#37d67a] px-4 text-[10px] font-semibold text-[#061109] transition-all hover:bg-[#44df84] disabled:cursor-not-allowed disabled:opacity-35"
                            >
                                {isLoading ? 'Connecting…' : connection ? 'Reconnect' : 'Connect'}
                            </button>
                            <button
                                type="button"
                                onClick={returnToSummary}
                                className="ml-1 grid h-9 w-8 shrink-0 place-items-center rounded-lg text-[16px] text-[var(--dash-text-muted)] transition-colors hover:bg-white/[0.04] hover:text-white"
                                aria-label="Cancel"
                            >
                                ×
                            </button>
                        </motion.form>
                    )}

                    {view === 'disconnect' && (
                        <motion.div
                            key="disconnect"
                            layout
                            initial={{ opacity: 0, filter: 'blur(5px)' }}
                            animate={{ opacity: 1, filter: 'blur(0px)' }}
                            exit={{ opacity: 0, filter: 'blur(5px)' }}
                            transition={{ duration: 0.22 }}
                            className="flex min-h-12 w-full items-center gap-2 p-1.5 sm:w-[380px]"
                        >
                            <div className="min-w-0 flex-1 px-2.5 leading-tight">
                                <p className="text-[11px] font-medium text-[var(--dash-text)]">Log out of Dhan?</p>
                                <p className="mt-0.5 truncate text-[8px] text-[var(--dash-text-muted)]">Your broker token will be removed.</p>
                            </div>
                            <button
                                type="button"
                                onClick={returnToSummary}
                                disabled={isLoading}
                                className="h-9 rounded-xl px-3 text-[10px] text-[var(--dash-text-secondary)] transition-colors hover:bg-white/[0.04] hover:text-white"
                            >
                                Cancel
                            </button>
                            <button
                                type="button"
                                onClick={handleDisconnect}
                                disabled={isLoading}
                                className="h-9 rounded-xl bg-[var(--dash-negative)] px-4 text-[10px] font-semibold text-[#180606] transition-opacity disabled:opacity-50"
                            >
                                {isLoading ? 'Logging out…' : 'Logout'}
                            </button>
                        </motion.div>
                    )}
                </AnimatePresence>
            </motion.div>

            <AnimatePresence>
                {error && (
                    <motion.p
                        id="dhan-connect-error"
                        initial={{ opacity: 0, y: -3 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -3 }}
                        className="absolute right-0 top-full mt-2 max-w-full text-right text-[9px] text-[var(--dash-negative)]"
                    >
                        {error}
                    </motion.p>
                )}
            </AnimatePresence>
        </motion.div>
    )
}
