'use client'

import { useState } from 'react'

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
        <div className="dash-surface p-6 h-full flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between mb-5">
                <div>
                    <span className="dash-label">Broker</span>
                    <h3 className="text-[20px] font-display text-[var(--dash-text)] tracking-[-0.02em] mt-1">
                        Connect to Dhan
                    </h3>
                </div>
                <span className="dash-badge dash-badge-positive">
                    <span className="dash-dot dash-dot-positive" style={{ width: 4, height: 4 }} />
                    Ready
                </span>
            </div>

            <p className="text-[13px] text-[var(--dash-text-secondary)] leading-relaxed mb-5">
                Link your Dhan trading account to enable live execution and AI-driven order routing.
            </p>

            {error && (
                <div className="mb-4 px-3 py-2.5 rounded-lg border border-[var(--dash-negative)]/20 bg-[var(--dash-negative)]/[0.04]">
                    <p className="text-[var(--dash-negative)] font-mono text-[12px]">
                        {error}
                    </p>
                </div>
            )}

            <form onSubmit={handleConnect} className="flex-1 flex flex-col gap-4">
                <div className="flex-1">
                    <label
                        htmlFor="clientId"
                        className="dash-label block mb-2"
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
                        className="dash-input"
                        aria-label="Enter your Dhan Client ID"
                    />
                    <p className="mt-1.5 text-[11px] text-[var(--dash-text-muted)]">
                        Find this in your Dhan account settings.
                    </p>
                </div>

                <button
                    type="submit"
                    disabled={isLoading || !clientId.trim()}
                    className="dash-btn-primary w-full"
                    aria-label="Connect to Dhan account"
                >
                    {isLoading ? (
                        <span className="flex items-center justify-center gap-2">
                            <svg
                                className="animate-spin h-3.5 w-3.5"
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
                            Connecting…
                        </span>
                    ) : (
                        'Connect Account'
                    )}
                </button>
            </form>

            <p className="mt-5 pt-4 border-t border-[var(--dash-border)] text-[11px] text-[var(--dash-text-muted)] leading-relaxed">
                🔒 Credentials encrypted end-to-end. We never see your Dhan password.
            </p>
        </div>
    )
}
