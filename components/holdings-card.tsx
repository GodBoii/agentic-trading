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

    const formatCurrency = (amount: number) => {
        return new Intl.NumberFormat('en-IN', {
            style: 'currency',
            currency: 'INR',
            maximumFractionDigits: 2,
        }).format(amount)
    }

    if (loading) {
        return (
            <div className="surface rounded-2xl p-7 lg:p-8 h-full">
                <div className="animate-pulse space-y-5">
                    <div className="h-3 w-24 bg-white/[0.06] rounded-full" />
                    <div className="h-6 w-32 bg-white/[0.04] rounded" />
                    <div className="space-y-2 mt-6">
                        <div className="h-14 bg-white/[0.03] rounded-xl" />
                        <div className="h-14 bg-white/[0.03] rounded-xl" />
                        <div className="h-14 bg-white/[0.03] rounded-xl" />
                    </div>
                </div>
            </div>
        )
    }

    if (error) {
        return (
            <div className="surface rounded-2xl p-7 lg:p-8 h-full">
                <div className="flex items-start justify-between mb-6">
                    <div>
                        <span className="text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary">
                            Portfolio · Long
                        </span>
                        <h3 className="font-display text-[24px] lg:text-[26px] text-white tracking-[-0.025em] leading-[1.1] mt-2">
                            Holdings
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
                        {error}
                    </p>
                </div>
            </div>
        )
    }

    return (
        <div className="surface rounded-2xl p-7 lg:p-8 h-full flex flex-col">
            {/* Header */}
            <div className="flex items-start justify-between mb-7">
                <div>
                    <span className="text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary">
                        Portfolio · Long
                    </span>
                    <div className="flex items-baseline gap-3 mt-2">
                        <h3 className="font-display text-[24px] lg:text-[26px] text-white tracking-[-0.025em] leading-[1.1]">
                            Holdings
                        </h3>
                        <span className="text-[12px] font-mono text-ink-tertiary nums">
                            {holdings.length} {holdings.length === 1 ? 'stock' : 'stocks'}
                        </span>
                    </div>
                </div>
                <button
                    onClick={fetchHoldings}
                    className="btn-secondary !px-3 !py-1.5 !text-[11px]"
                    aria-label="Refresh holdings data"
                >
                    <span>Refresh</span>
                    <span className="text-[10px]">↻</span>
                </button>
            </div>

            {holdings.length === 0 ? (
                <div className="flex-1 flex items-center justify-center border border-dashed border-line rounded-2xl py-16">
                    <div className="text-center max-w-xs">
                        <div className="mx-auto h-10 w-10 rounded-full border border-line flex items-center justify-center mb-4">
                            <svg className="w-4 h-4 text-ink-tertiary" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
                            </svg>
                        </div>
                        <p className="text-[13px] text-white font-medium mb-1">No holdings</p>
                        <p className="text-[12px] text-ink-tertiary">Your long-term portfolio is empty</p>
                    </div>
                </div>
            ) : (
                <div className="flex-1 -mx-2">
                    <div className="overflow-x-auto px-2">
                        <table className="w-full min-w-[500px]">
                            <thead>
                                <tr className="border-b border-line">
                                    <th className="text-left pb-3 text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary font-normal">
                                        Symbol
                                    </th>
                                    <th className="text-right pb-3 text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary font-normal">
                                        Qty
                                    </th>
                                    <th className="text-right pb-3 text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary font-normal">
                                        Avg Price
                                    </th>
                                    <th className="text-right pb-3 text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary font-normal">
                                        Value
                                    </th>
                                </tr>
                            </thead>
                            <tbody>
                                {holdings.map((holding, index) => (
                                    <tr
                                        key={index}
                                        className="border-b border-line/50 last:border-b-0 hover:bg-white/[0.015] transition-colors"
                                    >
                                        <td className="py-4 pr-3">
                                            <div>
                                                <p className="font-medium text-white font-mono text-[13px]">
                                                    {holding.tradingSymbol}
                                                </p>
                                                <p className="text-[10px] text-ink-tertiary font-mono uppercase tracking-[0.15em] mt-0.5">
                                                    {holding.exchange}
                                                </p>
                                            </div>
                                        </td>
                                        <td className="py-4 px-3 text-right">
                                            <p className="text-[13px] text-white font-mono nums">
                                                {holding.totalQty}
                                            </p>
                                            {holding.t1Qty > 0 && (
                                                <p className="text-[10px] text-warning font-mono mt-0.5">
                                                    T1 · {holding.t1Qty}
                                                </p>
                                            )}
                                        </td>
                                        <td className="py-4 px-3 text-right">
                                            <p className="text-[13px] text-white font-mono nums">
                                                {formatCurrency(holding.avgCostPrice)}
                                            </p>
                                        </td>
                                        <td className="py-4 pl-3 text-right">
                                            <p className="text-[13px] text-white font-mono nums font-medium">
                                                {formatCurrency(holding.totalQty * holding.avgCostPrice)}
                                            </p>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </div>
    )
}
