'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { topSegments, type CompositionSegment } from '@/components/charts/composition-bar'
import type { DivergingItem } from '@/components/charts/diverging-bars'
import type { OrderFlowPoint } from '@/components/charts/order-flow-timeline'
import { formatSegment, orderOutcome, type Funds, type Holding, type Order, type Position } from './types'

async function readApi<T>(url: string): Promise<T> {
    const response = await fetch(url, { cache: 'no-store' })
    const payload = await response.json().catch(() => null)
    if (!response.ok) throw new Error(payload?.error || 'Unable to load Dhan data')
    return payload as T
}

const asArray = <T,>(value: unknown): T[] => (Array.isArray(value) ? (value as T[]) : [])

export type PortfolioState = ReturnType<typeof usePortfolio>

/**
 * Loads the four Dhan endpoints and derives everything the Dashboard renders.
 *
 * Partial failure is a first-class outcome: each endpoint is settled
 * independently so an outage on, say, `/orders` still leaves funds, holdings
 * and positions on screen with a warning rather than blanking the page.
 */
export function usePortfolio() {
    const [funds, setFunds] = useState<Funds | null>(null)
    const [holdings, setHoldings] = useState<Holding[]>([])
    const [positions, setPositions] = useState<Position[]>([])
    const [orders, setOrders] = useState<Order[]>([])
    const [loading, setLoading] = useState(true)
    const [refreshing, setRefreshing] = useState(false)
    /** `fatal` means nothing loaded — usually "broker not connected". */
    const [error, setError] = useState<{ message: string; fatal: boolean } | null>(null)
    const [updatedAt, setUpdatedAt] = useState<Date | null>(null)

    const load = useCallback(async (background = false) => {
        if (background) setRefreshing(true)
        else setLoading(true)

        const results = await Promise.allSettled([
            readApi<Funds>('/api/dhan/funds'),
            readApi<Holding[]>('/api/dhan/holdings'),
            readApi<Position[]>('/api/dhan/positions'),
            readApi<Order[]>('/api/dhan/orders'),
        ])

        if (results[0].status === 'fulfilled') setFunds(results[0].value)
        if (results[1].status === 'fulfilled') setHoldings(asArray<Holding>(results[1].value))
        if (results[2].status === 'fulfilled') setPositions(asArray<Position>(results[2].value))
        if (results[3].status === 'fulfilled') setOrders(asArray<Order>(results[3].value))

        const failures = results.filter((result) => result.status === 'rejected') as PromiseRejectedResult[]
        if (failures.length === results.length) {
            const reason = failures[0].reason
            setError({
                message: reason instanceof Error ? reason.message : 'Connect Dhan to view your portfolio.',
                fatal: true,
            })
        } else if (failures.length) {
            setError({
                message: `${failures.length} of ${results.length} broker feeds did not respond. Showing the latest values that did.`,
                fatal: false,
            })
            setUpdatedAt(new Date())
        } else {
            setError(null)
            setUpdatedAt(new Date())
        }

        setLoading(false)
        setRefreshing(false)
    }, [])

    useEffect(() => {
        void load()
    }, [load])

    // Disconnecting the broker elsewhere in the UI must clear these figures
    // immediately rather than leaving stale money on screen.
    useEffect(() => {
        const onConnectionChange = (event: Event) => {
            const detail = (event as CustomEvent<{ connected?: boolean }>).detail
            if (detail?.connected !== false) return
            setFunds(null)
            setHoldings([])
            setPositions([])
            setOrders([])
            setUpdatedAt(null)
            setError({ message: 'Connect Dhan to view your live portfolio.', fatal: true })
        }
        window.addEventListener('dhan-connection-change', onConnectionChange)
        return () => window.removeEventListener('dhan-connection-change', onConnectionChange)
    }, [])

    const analytics = useMemo(() => {
        const invested = holdings.reduce((sum, item) => sum + item.totalQty * item.avgCostPrice, 0)
        const realized = positions.reduce((sum, item) => sum + item.realizedProfit, 0)
        const unrealized = positions.reduce((sum, item) => sum + item.unrealizedProfit, 0)
        const exposure = positions.reduce((sum, item) => {
            const reference = item.netQty >= 0 ? item.buyAvg : item.sellAvg
            return sum + Math.abs(item.netQty * reference)
        }, 0)

        const openPositions = positions.filter((item) => item.positionType !== 'CLOSED')
        const filledOrders = orders.filter((item) => orderOutcome(item.orderStatus) === 'filled')
        const workingOrders = orders.filter((item) => orderOutcome(item.orderStatus) === 'working')
        const failedOrders = orders.filter((item) => orderOutcome(item.orderStatus) === 'failed')

        const marginUse = funds?.sodLimit
            ? Math.min(100, Math.max(0, (funds.utilizedAmount / funds.sodLimit) * 100))
            : 0

        /** Where the account's capital currently sits. */
        const allCapital: CompositionSegment[] = funds
            ? [
                  { key: 'utilized', label: 'Utilized', value: funds.utilizedAmount, tone: 'warning' },
                  { key: 'available', label: 'Available', value: funds.availabelBalance, tone: 'positive' },
                  { key: 'collateral', label: 'Collateral', value: funds.collateralAmount, tone: 'accent' },
                  { key: 'receivable', label: 'Receivable', value: funds.receiveableAmount, tone: 'neutral' },
              ]
            : []
        const capitalSegments = allCapital.filter((segment) => segment.value > 0)

        /**
         * Concentration by invested value. At cost, not market value — the
         * broker payload carries no last-traded price, so anything claiming to
         * be current market weight would be fabricated.
         */
        const allocationSegments = topSegments(
            holdings
                .map((item) => ({
                    key: `${item.securityId}-${item.exchange}`,
                    label: item.tradingSymbol,
                    value: item.totalQty * item.avgCostPrice,
                    meta: `${item.totalQty}`,
                }))
                .filter((segment) => segment.value > 0),
            6,
        )

        /** Signed P&L per position, open and closed. */
        const positionPnl: DivergingItem[] = positions
            .map((item) => ({
                key: `${item.securityId}-${item.productType}`,
                label: item.tradingSymbol,
                value: item.realizedProfit + item.unrealizedProfit,
                meta: `${item.netQty} net · ${item.productType}`,
            }))
            .filter((item) => item.value !== 0)

        const orderPoints: OrderFlowPoint[] = orders.map((item) => {
            const outcome = orderOutcome(item.orderStatus)
            return {
                key: item.orderId,
                at: item.createTime,
                lane: item.transactionType === 'BUY' ? 'buy' : 'sell',
                tone:
                    outcome === 'filled'
                        ? 'positive'
                        : outcome === 'failed'
                          ? 'negative'
                          : outcome === 'working'
                            ? 'warning'
                            : 'neutral',
                title: `${item.tradingSymbol || item.securityId} · ${item.transactionType} ${item.quantity} · ${item.orderStatus.replaceAll('_', ' ')} · ${formatSegment(item.exchangeSegment)}`,
            }
        })

        const fillRate = orders.length ? (filledOrders.length / orders.length) * 100 : 0

        return {
            invested,
            realized,
            unrealized,
            dayPnl: realized + unrealized,
            exposure,
            openPositions,
            filledOrders,
            workingOrders,
            failedOrders,
            fillRate,
            marginUse,
            capitalSegments,
            allocationSegments,
            positionPnl,
            orderPoints,
        }
    }, [funds, holdings, positions, orders])

    return {
        funds,
        holdings,
        positions,
        orders,
        loading,
        refreshing,
        error,
        updatedAt,
        analytics,
        reload: load,
    }
}
