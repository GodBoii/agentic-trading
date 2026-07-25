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
                        <div className="h-16 bg-white/[0.02] rounded" />
                        <div className="h-16 bg-white/[0.02] rounded" />
                    </div>
                </div>
            </div>
        )
    }

    if (error) {
        return (
            <div className="dash-surface p-6 h-full">
                <div className="flex items-center justify-between mb-4">
                    <span className="dash-label">Positions</span>
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

    const totalUnrealized = positions.reduce((sum, pos) => sum + pos.unrealizedProfit, 0)
    const totalRealized = positions.reduce((sum, pos) => sum + pos.realizedProfit, 0)

    return (
        <div className="dash-surface p-6 h-full flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between mb-5">
                <div className="flex items-baseline gap-2.5">
                    <h3 className="text-[16px] font-medium text-[var(--dash-text)] tracking-[-0.01em]">
                        Positions
                    </h3>
                    <span className="text-[11px] font-mono text-[var(--dash-text-muted)] nums">
                        {positions.length}
                    </span>
                </div>
                <button
                    onClick={fetchPositions}
                    className="dash-btn !py-1 !px-2.5 !text-[11px]"
                    aria-label="Refresh positions data"
                >
                    ↻
                </button>
            </div>

            {/* P&L Summary */}
            {positions.length > 0 && (
                <div className="grid grid-cols-2 gap-4 mb-5">
                    <div>
                        <p className="dash-label mb-1">Unrealized P&L</p>
                        <p className={`text-[16px] font-medium nums ${totalUnrealized >= 0 ? 'text-[var(--dash-positive)]' : 'text-[var(--dash-negative)]'}`}>
                            {fmt(totalUnrealized)}
                        </p>
                    </div>
                    <div>
                        <p className="dash-label mb-1">Realized P&L</p>
                        <p className={`text-[16px] font-medium nums ${totalRealized >= 0 ? 'text-[var(--dash-positive)]' : 'text-[var(--dash-negative)]'}`}>
                            {fmt(totalRealized)}
                        </p>
                    </div>
                </div>
            )}

            {positions.length === 0 ? (
                <div className="flex-1 flex items-center justify-center py-12">
                    <div className="text-center">
                        <p className="text-[13px] text-[var(--dash-text-secondary)] mb-0.5">No open positions</p>
                        <p className="text-[11px] text-[var(--dash-text-muted)]">All positions closed for the day</p>
                    </div>
                </div>
            ) : (
                <div className="flex-1 space-y-2 overflow-y-auto">
                    {positions.map((pos, i) => {
                        const isLong = pos.positionType === 'LONG'
                        return (
                            <div
                                key={i}
                                className="rounded-xl border border-[var(--dash-border)] p-4 hover:border-[var(--dash-border-strong)] transition-colors"
                            >
                                <div className="flex justify-between items-start mb-3">
                                    <div>
                                        <p className="font-mono text-[13px] text-[var(--dash-text)] font-medium">{pos.tradingSymbol}</p>
                                        <div className="flex gap-1.5 mt-1.5">
                                            <span className={`dash-badge ${isLong ? 'dash-badge-positive' : 'dash-badge-negative'}`}>
                                                {pos.positionType}
                                            </span>
                                            <span className="dash-badge">{pos.productType}</span>
                                        </div>
                                    </div>
                                    <div className="text-right">
                                        <p className={`text-[16px] font-medium font-mono nums ${pos.unrealizedProfit >= 0 ? 'text-[var(--dash-positive)]' : 'text-[var(--dash-negative)]'}`}>
                                            {fmt(pos.unrealizedProfit)}
                                        </p>
                                        <p className="dash-label mt-0.5">Unrealized</p>
                                    </div>
                                </div>

                                <div className="grid grid-cols-3 gap-3 pt-3 border-t border-[var(--dash-border)]">
                                    <div>
                                        <p className="dash-label mb-0.5">Net Qty</p>
                                        <p className="text-[12px] font-mono text-[var(--dash-text)] nums">{pos.netQty}</p>
                                    </div>
                                    <div>
                                        <p className="dash-label mb-0.5">Buy Avg</p>
                                        <p className="text-[12px] font-mono text-[var(--dash-text)] nums">{fmt(pos.buyAvg)}</p>
                                    </div>
                                    <div>
                                        <p className="dash-label mb-0.5">Sell Avg</p>
                                        <p className="text-[12px] font-mono text-[var(--dash-text)] nums">{fmt(pos.sellAvg)}</p>
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
