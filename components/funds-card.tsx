'use client'

import { useState, useEffect } from 'react'

interface FundData {
    dhanClientId: string
    availabelBalance: number
    sodLimit: number
    collateralAmount: number
    receiveableAmount: number
    utilizedAmount: number
    blockedPayoutAmount: number
    withdrawableBalance: number
}

export default function FundsCard() {
    const [funds, setFunds] = useState<FundData | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        fetchFunds()
    }, [])

    const fetchFunds = async () => {
        try {
            setLoading(true)
            const response = await fetch('/api/dhan/funds')

            if (!response.ok) {
                const errorData = await response.json()
                throw new Error(errorData.error || 'Failed to fetch funds')
            }

            const data = await response.json()
            setFunds(data)
        } catch (err) {
            console.error('Error fetching funds:', err)
            setError(err instanceof Error ? err.message : 'An error occurred')
        } finally {
            setLoading(false)
        }
    }

    const fmt = (amount: number) => {
        return new Intl.NumberFormat('en-IN', {
            style: 'currency',
            currency: 'INR',
            maximumFractionDigits: 2,
        }).format(amount)
    }

    if (loading) {
        return (
            <div className="dash-surface p-6 lg:p-8">
                <div className="animate-pulse space-y-4">
                    <div className="h-3 w-24 bg-white/[0.04] rounded" />
                    <div className="h-10 w-56 bg-white/[0.03] rounded" />
                    <div className="grid grid-cols-4 gap-6 mt-6">
                        <div className="h-12 bg-white/[0.02] rounded" />
                        <div className="h-12 bg-white/[0.02] rounded" />
                        <div className="h-12 bg-white/[0.02] rounded" />
                        <div className="h-12 bg-white/[0.02] rounded" />
                    </div>
                </div>
            </div>
        )
    }

    if (error || !funds) {
        return (
            <div className="dash-surface p-6 lg:p-8">
                <div className="flex items-center justify-between mb-4">
                    <span className="dash-label">Account Funds</span>
                    <span className="dash-badge dash-badge-negative">Error</span>
                </div>
                <div className="px-3 py-2.5 rounded-lg bg-[rgba(248,113,113,0.04)] border border-[rgba(248,113,113,0.15)]">
                    <p className="text-[var(--dash-negative)] font-mono text-[12px]">
                        {error || 'No fund data available'}
                    </p>
                </div>
            </div>
        )
    }

    const metrics = [
        { label: 'Opening Balance', value: fmt(funds.sodLimit) },
        { label: 'Utilized', value: fmt(funds.utilizedAmount), accent: true },
        { label: 'Withdrawable', value: fmt(funds.withdrawableBalance) },
        { label: 'Collateral', value: fmt(funds.collateralAmount) },
    ]

    return (
        <div className="dash-surface p-6 lg:p-8">
            {/* Header row */}
            <div className="flex items-center justify-between mb-8">
                <span className="dash-label">Account Capital</span>
                <button
                    onClick={fetchFunds}
                    className="dash-btn !py-1 !px-2.5 !text-[11px]"
                    aria-label="Refresh fund data"
                >
                    ↻ Refresh
                </button>
            </div>

            {/* Hero metric */}
            <div className="mb-8">
                <p className="text-[11px] font-mono text-[var(--accent)] tracking-wide uppercase mb-2">
                    Available Balance
                </p>
                <p className="dash-metric text-[40px] lg:text-[48px] text-[var(--dash-text)] leading-none">
                    {fmt(funds.availabelBalance)}
                </p>
            </div>

            {/* Sub-metrics */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-6">
                {metrics.map((m) => (
                    <div key={m.label}>
                        <p className="dash-label mb-1.5">{m.label}</p>
                        <p className={`text-[16px] lg:text-[18px] font-medium tracking-[-0.01em] nums ${m.accent ? 'text-[var(--dash-warning)]' : 'text-[var(--dash-text)]'}`}>
                            {m.value}
                        </p>
                    </div>
                ))}
            </div>
        </div>
    )
}
