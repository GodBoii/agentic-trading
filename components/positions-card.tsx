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
                throw new Error('Failed to fetch positions')
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
            <div className="brutal-box p-8">
                <div className="animate-pulse space-y-4">
                    <div className="h-6 bg-brutal-cream/20 w-1/3"></div>
                    <div className="space-y-3">
                        <div className="h-16 bg-brutal-cream/10"></div>
                        <div className="h-16 bg-brutal-cream/10"></div>
                    </div>
                </div>
            </div>
        )
    }

    if (error) {
        return (
            <div className="brutal-box p-8">
                <div className="flex items-center gap-4 mb-4">
                    <div className="w-3 h-3 bg-brutal-red"></div>
                    <h3 className="text-2xl font-bold text-brutal-cream uppercase tracking-tight">Open Positions</h3>
                </div>
                <div className="brutal-box-sm border-brutal-red shadow-brutal-red p-4">
                    <p className="text-brutal-red font-mono text-sm font-bold uppercase">{error}</p>
                </div>
            </div>
        )
    }

    // Calculate totals
    const totalUnrealized = positions.reduce((sum, pos) => sum + pos.unrealizedProfit, 0)
    const totalRealized = positions.reduce((sum, pos) => sum + pos.realizedProfit, 0)

    return (
        <div className="brutal-box p-8">
            <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-4">
                    <div className="w-4 h-4 bg-brutal-yellow flex-shrink-0"></div>
                    <div>
                        <h3 className="text-2xl font-bold text-brutal-cream uppercase tracking-tight">Positions</h3>
                        <p className="text-sm text-brutal-cream/60 font-mono mt-1">{positions.length} active trades</p>
                    </div>
                </div>
                <button
                    onClick={fetchPositions}
                    className="brutal-btn px-4 py-2 text-xs"
                    aria-label="Refresh positions data"
                >
                    ↻ Refresh
                </button>
            </div>

            {/* P&L Summary */}
            {positions.length > 0 && (
                <div className="grid grid-cols-2 gap-4 mb-6">
                    <div className="brutal-box-sm border-brutal-cream/30 shadow-none p-4">
                        <p className="text-xs font-bold text-brutal-cream/60 mb-2 uppercase tracking-wide font-mono">
                            Unrealized P&L
                        </p>
                        <p className={`text-xl font-bold font-mono ${totalUnrealized >= 0 ? 'text-brutal-green' : 'text-brutal-red'
                            }`}>
                            {formatCurrency(totalUnrealized)}
                        </p>
                    </div>
                    <div className="brutal-box-sm border-brutal-cream/30 shadow-none p-4">
                        <p className="text-xs font-bold text-brutal-cream/60 mb-2 uppercase tracking-wide font-mono">
                            Realized P&L
                        </p>
                        <p className={`text-xl font-bold font-mono ${totalRealized >= 0 ? 'text-brutal-green' : 'text-brutal-red'
                            }`}>
                            {formatCurrency(totalRealized)}
                        </p>
                    </div>
                </div>
            )}

            {positions.length === 0 ? (
                <div className="brutal-box-sm border-brutal-cream/30 shadow-none p-12 text-center">
                    <div className="w-16 h-16 mx-auto border-4 border-brutal-cream/30 flex items-center justify-center mb-4">
                        <svg className="w-8 h-8 text-brutal-cream/30" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={3}>
                            <path strokeLinecap="square" strokeLinejoin="miter" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                        </svg>
                    </div>
                    <p className="text-brutal-cream/60 font-mono uppercase tracking-wide text-sm">No open positions</p>
                    <p className="text-brutal-cream/40 font-mono text-xs mt-2">All positions closed for the day</p>
                </div>
            ) : (
                <div className="space-y-4">
                    {positions.map((position, index) => (
                        <div key={index} className="brutal-box-sm border-brutal-cream/50 shadow-none p-5 hover:border-brutal-cream transition-colors">
                            <div className="flex justify-between items-start mb-4">
                                <div>
                                    <h4 className="font-bold text-brutal-cream text-xl font-mono">{position.tradingSymbol}</h4>
                                    <div className="flex gap-2 mt-2">
                                        <span className={`px-3 py-1 font-bold text-xs uppercase font-mono ${position.positionType === 'LONG'
                                                ? 'bg-brutal-green/20 text-brutal-green border-2 border-brutal-green'
                                                : 'bg-brutal-red/20 text-brutal-red border-2 border-brutal-red'
                                            }`}>
                                            {position.positionType}
                                        </span>
                                        <span className="px-3 py-1 bg-brutal-cream/10 text-brutal-cream border-2 border-brutal-cream/30 font-bold text-xs uppercase font-mono">
                                            {position.productType}
                                        </span>
                                    </div>
                                </div>
                                <div className="text-right">
                                    <p className={`text-2xl font-bold font-mono ${position.unrealizedProfit >= 0
                                            ? 'text-brutal-green'
                                            : 'text-brutal-red'
                                        }`}>
                                        {formatCurrency(position.unrealizedProfit)}
                                    </p>
                                    <p className="text-xs text-brutal-cream/50 font-mono uppercase tracking-wider mt-1">P&L</p>
                                </div>
                            </div>

                            <div className="grid grid-cols-3 gap-4 pt-4 border-t-2 border-brutal-cream/20">
                                <div>
                                    <p className="text-brutal-cream/60 text-xs font-mono uppercase tracking-wide mb-1">Net Qty</p>
                                    <p className="font-bold text-brutal-cream font-mono text-lg">{position.netQty}</p>
                                </div>
                                <div>
                                    <p className="text-brutal-cream/60 text-xs font-mono uppercase tracking-wide mb-1">Buy Avg</p>
                                    <p className="font-bold text-brutal-cream font-mono">{formatCurrency(position.buyAvg)}</p>
                                </div>
                                <div>
                                    <p className="text-brutal-cream/60 text-xs font-mono uppercase tracking-wide mb-1">Sell Avg</p>
                                    <p className="font-bold text-brutal-cream font-mono">{formatCurrency(position.sellAvg)}</p>
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}
