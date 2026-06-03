'use client'

import { useState } from 'react'
import { motion } from 'framer-motion'

const ease = [0.16, 1, 0.3, 1] as const

export default function DhanConnect() {
    const [clientId, setClientId] = useState('')
    const [isLoading, setIsLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)

    const handleConnect = async (e: React.FormEvent) => {
        e.preventDefault()
        setIsLoading(true)
        setError(null)

        try {
            const response = await fetch('/api/dhan/auth', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ dhanClientId: clientId }),
            })

            const data = await response.json()

            if (!response.ok) {
                throw new Error(data.error || 'Failed to initiate connection')
            }

            window.location.href = data.url

        } catch (err) {
            setError(err instanceof Error ? err.message : 'An error occurred')
            setIsLoading(false)
        }
    }

    return (
        <div className="surface rounded-2xl p-7 lg:p-8 h-full flex flex-col">
            {/* Header */}
            <div className="flex items-start justify-between mb-7">
                <div>
                    <span className="text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary">
                        Broker · Link
                    </span>
                    <h3 className="font-display text-[24px] lg:text-[26px] text-white tracking-[-0.025em] leading-[1.1] mt-2">
                        Connect to Dhan
                    </h3>
                </div>
                <div className="flex items-center gap-2 mt-1">
                    <span className="relative flex h-1.5 w-1.5">
                        <span className="absolute inline-flex h-full w-full rounded-full bg-success opacity-60 animate-pulse-ring" />
                        <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-success" />
                    </span>
                    <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-ink-tertiary">
                        Ready
                    </span>
                </div>
            </div>

            <p className="text-[13px] text-ink-secondary leading-relaxed mb-7">
                Link your Dhan trading account to enable live execution, real-time position sync, and AI-driven order routing.
            </p>

            {error && (
                <motion.div
                    initial={{ opacity: 0, y: -8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.4, ease }}
                    className="mb-6 border border-danger/40 bg-danger/[0.06] rounded-xl px-4 py-3"
                >
                    <p className="text-danger font-mono text-[12px] font-medium">
                        {error}
                    </p>
                </motion.div>
            )}

            <form onSubmit={handleConnect} className="space-y-5 flex-1 flex flex-col">
                <div className="flex-1">
                    <label
                        htmlFor="clientId"
                        className="block text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary mb-2.5"
                    >
                        Dhan Client ID
                    </label>
                    <input
                        id="clientId"
                        type="text"
                        value={clientId}
                        onChange={(e) => setClientId(e.target.value)}
                        placeholder="1000054321"
                        required
                        disabled={isLoading}
                        className="w-full bg-[#0a0a0c] border border-line hover:border-line-strong focus:border-accent/60 rounded-xl px-4 py-3.5 text-[14px] font-mono text-white placeholder:text-ink-tertiary transition-all duration-300 ease-out-expo focus:outline-none focus:ring-1 focus:ring-accent/30 disabled:opacity-50"
                        aria-label="Enter your Dhan Client ID"
                    />
                    <p className="mt-2.5 text-[11px] text-ink-tertiary font-mono">
                        Find this in your Dhan account settings.
                    </p>
                </div>

                <button
                    type="submit"
                    disabled={isLoading || !clientId.trim()}
                    className="btn-primary w-full disabled:opacity-40 disabled:cursor-not-allowed disabled:transform-none disabled:hover:shadow-none"
                    aria-label="Connect to Dhan account"
                >
                    {isLoading ? (
                        <span className="flex items-center justify-center gap-2.5">
                            <svg
                                className="animate-spin h-4 w-4"
                                xmlns="http://www.w3.org/2000/svg"
                                fill="none"
                                viewBox="0 0 24 24"
                            >
                                <circle
                                    className="opacity-25"
                                    cx="12"
                                    cy="12"
                                    r="10"
                                    stroke="currentColor"
                                    strokeWidth="3"
                                />
                                <path
                                    className="opacity-75"
                                    fill="currentColor"
                                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                                />
                            </svg>
                            <span>Connecting…</span>
                        </span>
                    ) : (
                        <>
                            <span>Connect Account</span>
                            <span className="text-[11px]">→</span>
                        </>
                    )}
                </button>
            </form>

            <div className="mt-7 pt-6 border-t border-line">
                <div className="flex gap-3">
                    <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-success flex-shrink-0" />
                    <div>
                        <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-ink-tertiary mb-1.5">
                            Secure Connection
                        </p>
                        <p className="text-[12px] text-ink-secondary leading-relaxed">
                            Your credentials are encrypted and stored securely. We never see your Dhan password.
                        </p>
                    </div>
                </div>
            </div>
        </div>
    )
}
