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
            <div className="brutal-box p-8">
                <div className="animate-pulse space-y-4">
                    <div className="h-6 bg-brutal-cream/20 w-1/3"></div>
                    <div className="space-y-3">
                        <div className="h-16 bg-brutal-cream/10"></div>
                        <div className="h-12 bg-brutal-cream/10"></div>
                        <div className="h-12 bg-brutal-cream/10"></div>
                    </div>
                </div>
            </div>
        )
    }

    if (error || !funds) {
        return (
            <div className="brutal-box p-8">
                <div className="flex items-center gap-4 mb-4">
                    <div className="w-3 h-3 bg-brutal-red"></div>
                    <h3 className="text-2xl font-bold text-brutal-cream uppercase tracking-tight">Account Funds</h3>
                </div>
                <div className="brutal-box-sm border-brutal-red shadow-brutal-red p-4">
                    <p className="text-brutal-red font-mono text-sm font-bold uppercase">
                        {error || 'No fund data available'}
                    </p>
                </div>
            </div>
        )
    }

    return (
        <div className="brutal-box p-8">
            <div className="flex items-center gap-4 mb-8">
                <div className="w-4 h-4 bg-brutal-green flex-shrink-0"></div>
                <div>
                    <h3 className="text-2xl font-bold text-brutal-cream uppercase tracking-tight">Account Funds</h3>
                    <p className="text-sm text-brutal-cream/60 font-mono mt-1">Trading account balance</p>
                </div>
            </div>

            <div className="space-y-6">
                {/* Available Balance - Highlighted */}
                <div className="brutal-box-sm border-brutal-green shadow-brutal-green p-6">
                    <div className="flex justify-between items-end">
                        <div>
                            <p className="text-xs font-bold text-brutal-green uppercase tracking-wider font-mono mb-2">
                                Available Balance
                            </p>
                            <p className="text-4xl font-bold text-brutal-green font-mono">
                                {formatCurrency(funds.availabelBalance)}
                            </p>
                        </div>
                        <div className="w-6 h-6 bg-brutal-green"></div>
                    </div>
                </div>

                {/* Other Fund Details */}
                <div className="grid grid-cols-2 gap-4">
                    <div className="brutal-box-sm border-brutal-cream/30 shadow-none p-4">
                        <p className="text-xs text-brutal-cream/60 mb-2 uppercase tracking-wide font-mono font-bold">
                            Opening Balance
                        </p>
                        <p className="text-xl font-bold text-brutal-cream font-mono">
                            {formatCurrency(funds.sodLimit)}
                        </p>
                    </div>

                    <div className="brutal-box-sm border-brutal-cream/30 shadow-none p-4">
                        <p className="text-xs text-brutal-cream/60 mb-2 uppercase tracking-wide font-mono font-bold">
                            Utilized Amount
                        </p>
                        <p className="text-xl font-bold text-brutal-red font-mono">
                            {formatCurrency(funds.utilizedAmount)}
                        </p>
                    </div>

                    <div className="brutal-box-sm border-brutal-cream/30 shadow-none p-4">
                        <p className="text-xs text-brutal-cream/60 mb-2 uppercase tracking-wide font-mono font-bold">
                            Withdrawable
                        </p>
                        <p className="text-xl font-bold text-brutal-cream font-mono">
                            {formatCurrency(funds.withdrawableBalance)}
                        </p>
                    </div>

                    <div className="brutal-box-sm border-brutal-cream/30 shadow-none p-4">
                        <p className="text-xs text-brutal-cream/60 mb-2 uppercase tracking-wide font-mono font-bold">
                            Collateral
                        </p>
                        <p className="text-xl font-bold text-brutal-cream font-mono">
                            {formatCurrency(funds.collateralAmount)}
                        </p>
                    </div>
                </div>

                {/* Refresh Button */}
                <button
                    onClick={fetchFunds}
                    className="brutal-btn w-full py-3 text-sm"
                    aria-label="Refresh fund data"
                >
                    ↻ Refresh Funds
                </button>
            </div>
        </div>
    )
}
