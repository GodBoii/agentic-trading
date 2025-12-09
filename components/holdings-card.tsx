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
                <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4">Holdings</h3>
                <p className="text-red-600 dark:text-red-400">{error}</p>
            </div>
        )
    }

    return (
        <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-lg p-6">
            <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                    <div className="w-12 h-12 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-full flex items-center justify-center">
                        <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 8v8m-4-5v5m-4-2v2m-2 4h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                        </svg>
                    </div>
                    <div>
                        <h3 className="text-xl font-bold text-gray-900 dark:text-white">Holdings</h3>
                        <p className="text-sm text-gray-600 dark:text-gray-400">{holdings.length} stocks</p>
                    </div>
                </div>
                <button
                    onClick={fetchHoldings}
                    className="px-3 py-1.5 bg-blue-100 dark:bg-blue-900/20 hover:bg-blue-200 dark:hover:bg-blue-900/40 text-blue-700 dark:text-blue-400 rounded-lg transition-all text-sm font-medium"
                >
                    🔄 Refresh
                </button>
            </div>

            {holdings.length === 0 ? (
                <div className="text-center py-8">
                    <svg className="w-16 h-16 mx-auto text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
                    </svg>
                    <p className="text-gray-600 dark:text-gray-400">No holdings found</p>
                    <p className="text-sm text-gray-500 dark:text-gray-500 mt-1">Your portfolio is empty</p>
                </div>
            ) : (
                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead>
                            <tr className="border-b border-gray-200 dark:border-gray-700">
                                <th className="text-left py-3 px-2 text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase">Symbol</th>
                                <th className="text-right py-3 px-2 text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase">Qty</th>
                                <th className="text-right py-3 px-2 text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase">Avg Price</th>
                                <th className="text-right py-3 px-2 text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase">Value</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                            {holdings.map((holding, index) => (
                                <tr key={index} className="hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                                    <td className="py-3 px-2">
                                        <div>
                                            <p className="font-semibold text-gray-900 dark:text-white">{holding.tradingSymbol}</p>
                                            <p className="text-xs text-gray-500 dark:text-gray-400">{holding.exchange}</p>
                                        </div>
                                    </td>
                                    <td className="py-3 px-2 text-right">
                                        <p className="font-medium text-gray-900 dark:text-white">{holding.totalQty}</p>
                                        {holding.t1Qty > 0 && (
                                            <p className="text-xs text-yellow-600 dark:text-yellow-400">T1: {holding.t1Qty}</p>
                                        )}
                                    </td>
                                    <td className="py-3 px-2 text-right">
                                        <p className="font-medium text-gray-900 dark:text-white">
                                            {formatCurrency(holding.avgCostPrice)}
                                        </p>
                                    </td>
                                    <td className="py-3 px-2 text-right">
                                        <p className="font-semibold text-gray-900 dark:text-white">
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
