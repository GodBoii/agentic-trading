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
            <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-lg p-6">
                <div className="animate-pulse space-y-4">
                    <div className="h-6 bg-gray-200 dark:bg-gray-700 rounded w-1/3"></div>
                    <div className="space-y-3">
                        <div className="h-16 bg-gray-200 dark:bg-gray-700 rounded"></div>
                        <div className="h-16 bg-gray-200 dark:bg-gray-700 rounded"></div>
                    </div>
                </div>
            </div>
        )
    }

    if (error) {
        return (
            <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-lg p-6">
                <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4">Open Positions</h3>
                <p className="text-red-600 dark:text-red-400">{error}</p>
            </div>
        )
    }

    // Calculate totals
    const totalUnrealized = positions.reduce((sum, pos) => sum + pos.unrealizedProfit, 0)
    const totalRealized = positions.reduce((sum, pos) => sum + pos.realizedProfit, 0)

    return (
        <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-lg p-6">
            <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                    <div className="w-12 h-12 bg-gradient-to-br from-purple-500 to-pink-600 rounded-full flex items-center justify-center">
                        <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                        </svg>
                    </div>
                    <div>
                        <h3 className="text-xl font-bold text-gray-900 dark:text-white">Open Positions</h3>
                        <p className="text-sm text-gray-600 dark:text-gray-400">{positions.length} active trades</p>
                    </div>
                </div>
                <button
                    onClick={fetchPositions}
                    className="px-3 py-1.5 bg-purple-100 dark:bg-purple-900/20 hover:bg-purple-200 dark:hover:bg-purple-900/40 text-purple-700 dark:text-purple-400 rounded-lg transition-all text-sm font-medium"
                >
                    🔄 Refresh
                </button>
            </div>

            {/* P&L Summary */}
            {positions.length > 0 && (
                <div className="grid grid-cols-2 gap-3 mb-6">
                    <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3">
                        <p className="text-xs text-gray-600 dark:text-gray-400 mb-1">Unrealized P&L</p>
                        <p className={`text-lg font-bold ${totalUnrealized >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                            {formatCurrency(totalUnrealized)}
                        </p>
                    </div>
                    <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3">
                        <p className="text-xs text-gray-600 dark:text-gray-400 mb-1">Realized P&L</p>
                        <p className={`text-lg font-bold ${totalRealized >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                            {formatCurrency(totalRealized)}
                        </p>
                    </div>
                </div>
            )}

            {positions.length === 0 ? (
                <div className="text-center py-8">
                    <svg className="w-16 h-16 mx-auto text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    <p className="text-gray-600 dark:text-gray-400">No open positions</p>
                    <p className="text-sm text-gray-500 dark:text-gray-500 mt-1">All positions closed for the day</p>
                </div>
            ) : (
                <div className="overflow-x-auto">
                    <div className="space-y-3">
                        {positions.map((position, index) => (
                            <div key={index} className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                                <div className="flex justify-between items-start mb-3">
                                    <div>
                                        <h4 className="font-bold text-gray-900 dark:text-white">{position.tradingSymbol}</h4>
                                        <div className="flex gap-2 mt-1">
                                            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${position.positionType === 'LONG'
                                                    ? 'bg-green-100 dark:bg-green-900/20 text-green-700 dark:text-green-400'
                                                    : 'bg-red-100 dark:bg-red-900/20 text-red-700 dark:text-red-400'
                                                }`}>
                                                {position.positionType}
                                            </span>
                                            <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 font-medium">
                                                {position.productType}
                                            </span>
                                        </div>
                                    </div>
                                    <div className="text-right">
                                        <p className={`text-lg font-bold ${position.unrealizedProfit >= 0
                                                ? 'text-green-600 dark:text-green-400'
                                                : 'text-red-600 dark:text-red-400'
                                            }`}>
                                            {formatCurrency(position.unrealizedProfit)}
                                        </p>
                                        <p className="text-xs text-gray-500 dark:text-gray-400">P&L</p>
                                    </div>
                                </div>

                                <div className="grid grid-cols-3 gap-4 text-sm">
                                    <div>
                                        <p className="text-gray-600 dark:text-gray-400 text-xs">Net Qty</p>
                                        <p className="font-semibold text-gray-900 dark:text-white">{position.netQty}</p>
                                    </div>
                                    <div>
                                        <p className="text-gray-600 dark:text-gray-400 text-xs">Buy Avg</p>
                                        <p className="font-semibold text-gray-900 dark:text-white">{formatCurrency(position.buyAvg)}</p>
                                    </div>
                                    <div>
                                        <p className="text-gray-600 dark:text-gray-400 text-xs">Sell Avg</p>
                                        <p className="font-semibold text-gray-900 dark:text-white">{formatCurrency(position.sellAvg)}</p>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    )
}
