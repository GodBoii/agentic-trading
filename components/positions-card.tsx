'use client'

import { useState, useEffect } from 'react'

interface Position {
    dhanClientId: string
    tradingSymbol: string
    securityId: string
    positionType: string
    exchangeSegment: string
    productType: string
    buyAvg: number
    buyQty: number
    sellAvg: number
    sellQty: number
    netQty: number
    realizedProfit: number
    unrealizedProfit: number
}

export default function PositionsCard() {
    const [positions, setPositions] = useState<Position[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        fetchPositions()
    }, [])

    const fetchPositions = async () => {
        try {
            setLoading(true)
            const response = await fetch('/api/dhan/positions')

            if (!response.ok) {
                const errorData = await response.json()
                throw new Error(errorData.error || 'Failed to fetch positions')
            }

            const data = await response.json()
            setPositions(Array.isArray(data) ? data : [])
        } catch (err) {
            console.error('Error fetching positions:', err)
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
                        <div className="h-20 bg-white/[0.03] rounded-xl" />
                        <div className="h-20 bg-white/[0.03] rounded-xl" />
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
                            Portfolio · Active
                        </span>
                        <h3 className="font-display text-[24px] lg:text-[26px] text-white tracking-[-0.025em] leading-[1.1] mt-2">
                            Open Positions
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

    const totalUnrealized = positions.reduce((sum, pos) => sum + pos.unrealizedProfit, 0)
    const totalRealized = positions.reduce((sum, pos) => sum + pos.realizedProfit, 0)

    return (
        <div className="surface rounded-2xl p-7 lg:p-8 h-full flex flex-col">
            {/* Header */}
            <div className="flex items-start justify-between mb-7">
                <div>
                    <span className="text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary">
                        Portfolio · Active
                    </span>
                    <div className="flex items-baseline gap-3 mt-2">
                        <h3 className="font-display text-[24px] lg:text-[26px] text-white tracking-[-0.025em] leading-[1.1]">
                            Positions
                        </h3>
                        <span className="text-[12px] font-mono text-ink-tertiary nums">
                            {positions.length} {positions.length === 1 ? 'trade' : 'trades'}
                        </span>
                    </div>
                </div>
                <button
                    onClick={fetchPositions}
                    className="btn-secondary !px-3 !py-1.5 !text-[11px]"
                    aria-label="Refresh positions data"
                >
                    <span>Refresh</span>
                    <span className="text-[10px]">↻</span>
                </button>
            </div>

            {/* P&L Summary */}
            {positions.length > 0 && (
                <div className="grid grid-cols-2 gap-px bg-line rounded-xl overflow-hidden border border-line mb-7">
                    <PnLCell label="Unrealized P&L" value={formatCurrency(totalUnrealized)} valueClass={totalUnrealized >= 0 ? 'text-success' : 'text-danger'} />
                    <PnLCell label="Realized P&L" value={formatCurrency(totalRealized)} valueClass={totalRealized >= 0 ? 'text-success' : 'text-danger'} />
                </div>
            )}

            {positions.length === 0 ? (
                <div className="flex-1 flex items-center justify-center border border-dashed border-line rounded-2xl py-16">
                    <div className="text-center max-w-xs">
                        <div className="mx-auto h-10 w-10 rounded-full border border-line flex items-center justify-center mb-4">
                            <svg className="w-4 h-4 text-ink-tertiary" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                            </svg>
                        </div>
                        <p className="text-[13px] text-white font-medium mb-1">No open positions</p>
                        <p className="text-[12px] text-ink-tertiary">All positions closed for the day</p>
                    </div>
                </div>
            ) : (
                <div className="flex-1 space-y-2.5 overflow-y-auto -mx-1 px-1">
                    {positions.map((position, index) => {
                        const isLong = position.positionType === 'LONG'
                        return (
                            <div
                                key={index}
                                className="rounded-xl border border-line bg-[#0a0a0c]/40 hover:border-line-strong hover:bg-[#0c0c0e] transition-all duration-300 p-5"
                            >
                                <div className="flex justify-between items-start gap-3 mb-4">
                                    <div className="flex-1 min-w-0">
                                        <h4 className="font-medium text-white text-[14px] font-mono truncate">
                                            {position.tradingSymbol}
                                        </h4>
                                        <div className="flex gap-1.5 mt-2.5 flex-wrap">
                                            <span className={`text-[10px] font-mono uppercase tracking-[0.15em] px-2 py-0.5 rounded-full border ${isLong
                                                ? 'border-success/40 bg-success/10 text-success'
                                                : 'border-danger/40 bg-danger/10 text-danger'
                                                }`}>
                                                {position.positionType}
                                            </span>
                                            <span className="text-[10px] font-mono uppercase tracking-[0.15em] px-2 py-0.5 rounded-full border border-line text-ink-secondary">
                                                {position.productType}
                                            </span>
                                        </div>
                                    </div>
                                    <div className="text-right flex-shrink-0">
                                        <p className={`text-[18px] font-medium font-mono nums ${position.unrealizedProfit >= 0
                                            ? 'text-success'
                                            : 'text-danger'
                                            }`}>
                                            {formatCurrency(position.unrealizedProfit)}
                                        </p>
                                        <p className="text-[10px] text-ink-tertiary font-mono uppercase tracking-[0.15em] mt-1">
                                            Unrealized
                                        </p>
                                    </div>
                                </div>

                                <div className="grid grid-cols-3 gap-4 pt-4 border-t border-line/60">
                                    <div>
                                        <p className="text-ink-tertiary text-[10px] font-mono uppercase tracking-[0.15em] mb-1">
                                            Net Qty
                                        </p>
                                        <p className="text-white font-mono text-[13px] nums">
                                            {position.netQty}
                                        </p>
                                    </div>
                                    <div>
                                        <p className="text-ink-tertiary text-[10px] font-mono uppercase tracking-[0.15em] mb-1">
                                            Buy Avg
                                        </p>
                                        <p className="text-white font-mono text-[13px] nums">
                                            {formatCurrency(position.buyAvg)}
                                        </p>
                                    </div>
                                    <div>
                                        <p className="text-ink-tertiary text-[10px] font-mono uppercase tracking-[0.15em] mb-1">
                                            Sell Avg
                                        </p>
                                        <p className="text-white font-mono text-[13px] nums">
                                            {formatCurrency(position.sellAvg)}
                                        </p>
                                    </div>
                                </div>
                            </div>
                        )
                    })}
                </div>
            )}
        </div>
    )
}

function PnLCell({ label, value, valueClass }: { label: string; value: string; valueClass: string }) {
    return (
        <div className="bg-[#08080a] p-4 flex flex-col gap-1.5">
            <span className="text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary">
                {label}
            </span>
            <span className={`text-[16px] font-medium nums ${valueClass}`}>
                {value}
            </span>
        </div>
    )
}
