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
        <div className="brutal-box p-8 space-y-6">
            <div className="flex items-center gap-4">
                <div className="w-3 h-3 bg-brutal-green flex-shrink-0"></div>
                <div>
                    <h3 className="text-2xl font-bold text-brutal-cream uppercase tracking-tight">
                        Connect to Dhan
                    </h3>
                    <p className="text-sm text-brutal-cream/60 font-mono mt-1">
                        Link your trading account
                    </p>
                </div>
            </div>

            {error && (
                <div className="brutal-box-sm border-brutal-red shadow-brutal-red p-4 animate-shake">
                    <p className="text-brutal-red font-mono text-sm font-bold uppercase">
                        {error}
                    </p>
                </div>
            )}

            <form onSubmit={handleConnect} className="space-y-6">
                <div>
                    <label
                        htmlFor="clientId"
                        className="block text-sm font-bold text-brutal-cream mb-3 uppercase tracking-wider font-mono"
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
                        className="brutal-input w-full px-4 py-4 text-lg disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                        aria-label="Enter your Dhan Client ID"
                    />
                    <p className="mt-3 text-xs text-brutal-cream/50 font-mono uppercase tracking-wide">
                        Find your ID in Dhan account settings
                    </p>
                </div>

                <button
                    type="submit"
                    disabled={isLoading || !clientId.trim()}
                    className="brutal-btn w-full py-4 text-base disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none disabled:shadow-brutal"
                    aria-label="Connect to Dhan account"
                >
                    {isLoading ? (
                        <span className="flex items-center justify-center gap-3">
                            <svg
                                className="animate-spin h-5 w-5 text-brutal-black"
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
                                    strokeWidth="4"
                                />
                                <path
                                    className="opacity-75"
                                    fill="currentColor"
                                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                                />
                            </svg>
                            Connecting...
                        </span>
                    ) : (
                        'Connect Account'
                    )}
                </button>
            </form>

            <div className="brutal-box-sm border-brutal-cream/30 shadow-none p-4">
                <div className="flex gap-3">
                    <div className="w-2 h-2 bg-brutal-green flex-shrink-0 mt-1"></div>
                    <div className="text-xs text-brutal-cream/70 font-mono leading-relaxed">
                        <p className="font-bold mb-2 uppercase tracking-wide">Secure Connection</p>
                        <p>
                            Your credentials are encrypted and stored securely. We never see your Dhan password.
                        </p>
                    </div>
                </div>
            </div>
        </div>
    )
}
