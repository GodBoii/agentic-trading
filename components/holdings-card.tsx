'use client'

import { useState, useEffect } from 'react'

interface Holding {
    exchange: string
    tradingSymbol: string
    securityId: string
    isin: string
    totalQty: number
    dpQty: number
    t1Qty: number
    availableQty: number
    collateralQty: number
    avgCostPrice: number
}

export default function HoldingsCard() {
    const [holdings, setHoldings] = useState<Holding[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        fetchHoldings()
    }, [])

    const fetchHoldings = async () => {
        try {
            setLoading(true)
            const response = await fetch('/api/dhan/holdings')

            if (!response.ok) {
                const errorData = await response.json()
                throw new Error(errorData.error || 'Failed to fetch holdings')
            }

            const data = await response.json()
            setHoldings(Array.isArray(data) ? data : [])
        } catch (err) {
            console.error('Error fetching holdings:', err)
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
            <div className="dash-surface p-6 h-full">
                <div className="animate-pulse space-y-3">
                    <div className="h-3 w-20 bg-white/[0.04] rounded" />
                    <div className="h-5 w-28 bg-white/[0.03] rounded" />
                    <div className="space-y-2 mt-4">
                        <div className="h-10 bg-white/[0.02] rounded" />
                        <div className="h-10 bg-white/[0.02] rounded" />
                        <div className="h-10 bg-white/[0.02] rounded" />
                    </div>
                </div>
            </div>
        )
    }

    if (error) {
        return (
            <div className="dash-surface p-6 h-full">
                <div className="flex items-center justify-between mb-4">
                    <span className="dash-label">Holdings</span>
                    <span className="dash-badge dash-badge-negative">Error</span>
                </div>
                <div className="px-3 py-2.5 rounded-lg bg-[rgba(248,113,113,0.04)] border border-[rgba(248,113,113,0.15)]">
                    <p className="text-[var(--dash-negative)] font-mono text-[12px]">
                        {error}
                    </p>
                </div>
            </div>
        )
    }

    return (
        <div className="dash-surface p-6 h-full flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between mb-5">
                <div className="flex items-baseline gap-2.5">
                    <h3 className="text-[16px] font-medium text-[var(--dash-text)] tracking-[-0.01em]">
                        Holdings
                    </h3>
                    <span className="text-[11px] font-mono text-[var(--dash-text-muted)] nums">
                        {holdings.length}
                    </span>
                </div>
                <button
                    onClick={fetchHoldings}
                    className="dash-btn !py-1 !px-2.5 !text-[11px]"
                    aria-label="Refresh holdings data"
                >
                    ↻
                </button>
            </div>

            {holdings.length === 0 ? (
                <div className="flex-1 flex items-center justify-center py-12">
                    <div className="text-center">
                        <p className="text-[13px] text-[var(--dash-text-secondary)] mb-0.5">No holdings</p>
                        <p className="text-[11px] text-[var(--dash-text-muted)]">Your long-term portfolio is empty</p>
                    </div>
                </div>
            ) : (
                <div className="flex-1 -mx-1 overflow-x-auto">
                    <table className="w-full min-w-[460px]">
                        <thead>
                            <tr>
                                <th className="text-left pb-2.5 dash-label font-normal">Symbol</th>
                                <th className="text-right pb-2.5 dash-label font-normal">Qty</th>
                                <th className="text-right pb-2.5 dash-label font-normal">Avg Price</th>
                                <th className="text-right pb-2.5 dash-label font-normal">Value</th>
                            </tr>
                        </thead>
                        <tbody>
                            {holdings.map((h, i) => (
                                <tr
                                    key={i}
                                    className="border-t border-[var(--dash-border)] hover:bg-white/[0.01] transition-colors"
                                >
                                    <td className="py-3 pr-3">
                                        <p className="font-mono text-[13px] text-[var(--dash-text)] font-medium">{h.tradingSymbol}</p>
                                        <p className="text-[10px] text-[var(--dash-text-muted)] font-mono mt-0.5">{h.exchange}</p>
                                    </td>
                                    <td className="py-3 px-2 text-right">
                                        <span className="font-mono text-[13px] text-[var(--dash-text)] nums">{h.totalQty}</span>
                                        {h.t1Qty > 0 && (
                                            <span className="block text-[10px] text-[var(--dash-warning)] font-mono mt-0.5">
                                                T1 · {h.t1Qty}
                                            </span>
                                        )}
                                    </td>
                                    <td className="py-3 px-2 text-right font-mono text-[13px] text-[var(--dash-text)] nums">
                                        {fmt(h.avgCostPrice)}
                                    </td>
                                    <td className="py-3 pl-2 text-right font-mono text-[13px] text-[var(--dash-text)] nums font-medium">
                                        {fmt(h.totalQty * h.avgCostPrice)}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    )
}
