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
                throw new Error('Failed to fetch holdings')
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
                    <h3 className="text-2xl font-bold text-brutal-cream uppercase tracking-tight">Holdings</h3>
                </div>
                <div className="brutal-box-sm border-brutal-red shadow-brutal-red p-4">
                    <p className="text-brutal-red font-mono text-sm font-bold uppercase">{error}</p>
                </div>
            </div>
        )
    }

    return (
        <div className="brutal-box p-8">
            <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-4">
                    <div className="w-4 h-4 bg-brutal-cream flex-shrink-0"></div>
                    <div>
                        <h3 className="text-2xl font-bold text-brutal-cream uppercase tracking-tight">Holdings</h3>
                        <p className="text-sm text-brutal-cream/60 font-mono mt-1">{holdings.length} stocks</p>
                    </div>
                </div>
                <button
                    onClick={fetchHoldings}
                    className="brutal-btn px-4 py-2 text-xs"
                    aria-label="Refresh holdings data"
                >
                    ↻ Refresh
                </button>
            </div>

            {holdings.length === 0 ? (
                <div className="brutal-box-sm border-brutal-cream/30 shadow-none p-12 text-center">
                    <div className="w-16 h-16 mx-auto border-4 border-brutal-cream/30 flex items-center justify-center mb-4">
                        <svg className="w-8 h-8 text-brutal-cream/30" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={3}>
                            <path strokeLinecap="square" strokeLinejoin="miter" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
                        </svg>
                    </div>
                    <p className="text-brutal-cream/60 font-mono uppercase tracking-wide text-sm">No holdings found</p>
                    <p className="text-brutal-cream/40 font-mono text-xs mt-2">Your portfolio is empty</p>
                </div>
            ) : (
                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead>
                            <tr className="border-b-3 border-brutal-cream/30">
                                <th className="text-left py-4 px-3 text-xs font-bold text-brutal-cream uppercase tracking-wider font-mono">Symbol</th>
                                <th className="text-right py-4 px-3 text-xs font-bold text-brutal-cream uppercase tracking-wider font-mono">Qty</th>
                                <th className="text-right py-4 px-3 text-xs font-bold text-brutal-cream uppercase tracking-wider font-mono">Avg Price</th>
                                <th className="text-right py-4 px-3 text-xs font-bold text-brutal-cream uppercase tracking-wider font-mono">Value</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y-2 divide-brutal-cream/10">
                            {holdings.map((holding, index) => (
                                <tr key={index} className="hover:bg-brutal-cream/5 transition-colors">
                                    <td className="py-4 px-3">
                                        <div>
                                            <p className="font-bold text-brutal-cream font-mono">{holding.tradingSymbol}</p>
                                            <p className="text-xs text-brutal-cream/50 font-mono uppercase">{holding.exchange}</p>
                                        </div>
                                    </td>
                                    <td className="py-4 px-3 text-right">
                                        <p className="font-bold text-brutal-cream font-mono">{holding.totalQty}</p>
                                        {holding.t1Qty > 0 && (
                                            <p className="text-xs text-brutal-yellow font-mono uppercase">T1: {holding.t1Qty}</p>
                                        )}
                                    </td>
                                    <td className="py-4 px-3 text-right">
                                        <p className="font-bold text-brutal-cream font-mono">
                                            {formatCurrency(holding.avgCostPrice)}
                                        </p>
                                    </td>
                                    <td className="py-4 px-3 text-right">
                                        <p className="font-bold text-brutal-green font-mono">
                                            {formatCurrency(holding.totalQty * holding.avgCostPrice)}
                                        </p>
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
