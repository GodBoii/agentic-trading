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

    const formatCurrency = (amount: number) => {
        return new Intl.NumberFormat('en-IN', {
            style: 'currency',
            currency: 'INR',
            maximumFractionDigits: 2,
        }).format(amount)
    }

    if (loading) {
        return (
            <div className="surface rounded-2xl p-7 lg:p-8">
                <div className="animate-pulse space-y-5">
                    <div className="h-3 w-32 bg-white/[0.06] rounded-full" />
                    <div className="h-8 w-48 bg-white/[0.04] rounded" />
                    <div className="h-28 bg-white/[0.03] rounded-xl" />
                    <div className="grid grid-cols-2 gap-3">
                        <div className="h-20 bg-white/[0.03] rounded-xl" />
                        <div className="h-20 bg-white/[0.03] rounded-xl" />
                    </div>
                </div>
            </div>
        )
    }

    if (error || !funds) {
        return (
            <div className="surface rounded-2xl p-7 lg:p-8">
                <div className="flex items-start justify-between mb-6">
                    <div>
                        <span className="text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary">
                            Account · Capital
                        </span>
                        <h3 className="font-display text-[24px] lg:text-[26px] text-white tracking-[-0.025em] leading-[1.1] mt-2">
                            Account Funds
                        </h3>
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                        <span className="h-1.5 w-1.5 rounded-full bg-danger" />
                        <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-ink-tertiary">
                            Error
                        </span>
                    </div>
                </div>
                <div className="border border-danger/40 bg-danger/[0.06] rounded-xl px-4 py-3">
                    <p className="text-danger font-mono text-[12px] font-medium">
                        {error || 'No fund data available'}
                    </p>
                </div>
            </div>
        )
    }

    return (
        <div className="surface rounded-2xl p-7 lg:p-10">
            {/* Header */}
            <div className="flex items-start justify-between mb-10">
                <div>
                    <span className="text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary">
                        Account · Capital
                    </span>
                    <h3 className="font-display text-[28px] lg:text-[32px] text-white tracking-[-0.03em] leading-[1.05] mt-2">
                        Account Funds
                    </h3>
                </div>
                <div className="flex items-center gap-2 mt-1">
                    <span className="relative flex h-1.5 w-1.5">
                        <span className="absolute inline-flex h-full w-full rounded-full bg-success opacity-60 animate-pulse-ring" />
                        <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-success" />
                    </span>
                    <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-ink-tertiary">
                        Live
                    </span>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-10">
                {/* Available Balance - Hero metric */}
                <div className="lg:col-span-5">
                    <div className="border border-accent/20 bg-gradient-to-br from-accent/[0.06] to-transparent rounded-2xl p-7 h-full flex flex-col justify-between min-h-[200px]">
                        <div>
                            <span className="text-[10px] font-mono uppercase tracking-[0.22em] text-accent">
                                Available Balance
                            </span>
                            <p className="font-display text-[40px] lg:text-[52px] text-white tracking-[-0.035em] leading-[1] mt-4 nums">
                                {formatCurrency(funds.availabelBalance)}
                            </p>
                        </div>
                        <div className="flex items-center gap-2 mt-6">
                            <span className="h-1 w-1 rounded-full bg-accent" />
                            <span className="text-[11px] font-mono uppercase tracking-[0.18em] text-ink-tertiary">
                                Deployable capital
                            </span>
                        </div>
                    </div>
                </div>

                {/* Other metrics */}
                <div className="lg:col-span-7 grid grid-cols-2 gap-px bg-line rounded-2xl overflow-hidden border border-line">
                    <MetricCell
                        label="Opening Balance"
                        value={formatCurrency(funds.sodLimit)}
                    />
                    <MetricCell
                        label="Utilized"
                        value={formatCurrency(funds.utilizedAmount)}
                        accent="text-warning"
                    />
                    <MetricCell
                        label="Withdrawable"
                        value={formatCurrency(funds.withdrawableBalance)}
                    />
                    <MetricCell
                        label="Collateral"
                        value={formatCurrency(funds.collateralAmount)}
                    />
                </div>
            </div>

            {/* Refresh */}
            <div className="mt-8 pt-7 border-t border-line">
                <button
                    onClick={fetchFunds}
                    className="btn-secondary !px-4 !py-2 !text-[12px]"
                    aria-label="Refresh fund data"
                >
                    <span>Refresh</span>
                    <span className="text-[11px]">↻</span>
                </button>
            </div>
        </div>
    )
}

function MetricCell({ label, value, accent = 'text-white' }: { label: string; value: string; accent?: string }) {
    return (
        <div className="bg-[#08080a] p-5 lg:p-6 flex flex-col gap-2.5 hover:bg-[#0c0c0e] transition-colors duration-500">
            <span className="text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary">
                {label}
            </span>
            <span className={`text-[18px] lg:text-[20px] font-medium tracking-[-0.02em] nums ${accent}`}>
                {value}
            </span>
        </div>
    )
}
