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
                throw new Error('Failed to fetch funds')
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
            <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-lg p-6">
                <div className="animate-pulse space-y-4">
                    <div className="h-6 bg-gray-200 dark:bg-gray-700 rounded w-1/3"></div>
                    <div className="space-y-3">
                        <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded"></div>
                        <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded"></div>
                        <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded"></div>
                    </div>
                </div>
            </div>
        )
    }

    if (error || !funds) {
        return (
            <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-lg p-6">
                <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4">Account Funds</h3>
                <p className="text-red-600 dark:text-red-400">
                    {error || 'No fund data available'}
                </p>
            </div>
        )
    }

    return (
        <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-lg p-6">
            <div className="flex items-center gap-3 mb-6">
                <div className="w-12 h-12 bg-gradient-to-br from-green-500 to-emerald-600 rounded-full flex items-center justify-center">
                    <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                </div>
                <div>
                    <h3 className="text-xl font-bold text-gray-900 dark:text-white">Account Funds</h3>
                    <p className="text-sm text-gray-600 dark:text-gray-400">Trading account balance</p>
                </div>
            </div>

            <div className="space-y-4">
                {/* Available Balance - Highlighted */}
                <div className="bg-gradient-to-r from-green-50 to-emerald-50 dark:from-green-900/20 dark:to-emerald-900/20 rounded-lg p-4 border-2 border-green-500">
                    <div className="flex justify-between items-center">
                        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Available Balance</span>
                        <span className="text-2xl font-bold text-green-600 dark:text-green-400">
                            {formatCurrency(funds.availabelBalance)}
                        </span>
                    </div>
                </div>

                {/* Other Fund Details */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3">
                        <p className="text-xs text-gray-600 dark:text-gray-400 mb-1">Opening Balance</p>
                        <p className="text-lg font-semibold text-gray-900 dark:text-white">
                            {formatCurrency(funds.sodLimit)}
                        </p>
                    </div>

                    <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3">
                        <p className="text-xs text-gray-600 dark:text-gray-400 mb-1">Utilized Amount</p>
                        <p className="text-lg font-semibold text-red-600 dark:text-red-400">
                            {formatCurrency(funds.utilizedAmount)}
                        </p>
                    </div>

                    <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3">
                        <p className="text-xs text-gray-600 dark:text-gray-400 mb-1">Withdrawable Balance</p>
                        <p className="text-lg font-semibold text-blue-600 dark:text-blue-400">
                            {formatCurrency(funds.withdrawableBalance)}
                        </p>
                    </div>

                    <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3">
                        <p className="text-xs text-gray-600 dark:text-gray-400 mb-1">Collateral Amount</p>
                        <p className="text-lg font-semibold text-gray-900 dark:text-white">
                            {formatCurrency(funds.collateralAmount)}
                        </p>
                    </div>
                </div>

                {/* Refresh Button */}
                <button
                    onClick={fetchFunds}
                    className="w-full mt-4 px-4 py-2 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-900 dark:text-white rounded-lg transition-all font-medium text-sm"
                >
                    🔄 Refresh Funds
                </button>
            </div>
        </div>
    )
}
