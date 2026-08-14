/**
 * Dhan API response shapes.
 *
 * These mirror the broker payload exactly and are passed through unchanged by
 * `app/api/dhan/*`. Note `availabelBalance` — the typo is upstream, in Dhan's
 * own response, and must not be "corrected" here.
 */

export type Funds = {
    dhanClientId: string
    availabelBalance: number
    sodLimit: number
    collateralAmount: number
    receiveableAmount: number
    utilizedAmount: number
    withdrawableBalance: number
}

export type Holding = {
    exchange: string
    tradingSymbol: string
    securityId: string
    totalQty: number
    dpQty: number
    t1Qty: number
    availableQty: number
    collateralQty: number
    avgCostPrice: number
}

export type Position = {
    tradingSymbol: string
    securityId: string
    positionType: 'LONG' | 'SHORT' | 'CLOSED'
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

export type Order = {
    orderId: string
    orderStatus: string
    transactionType: 'BUY' | 'SELL'
    exchangeSegment: string
    productType: string
    orderType: string
    tradingSymbol: string
    securityId: string
    quantity: number
    price: number
    averageTradedPrice: number
    filledQty: number
    createTime: string
    omsErrorDescription?: string | null
}

export const OPEN_ORDER_STATUSES = ['PENDING', 'TRANSIT', 'PART_TRADED'] as const
export const FAILED_ORDER_STATUSES = ['REJECTED', 'CANCELLED', 'EXPIRED'] as const

export type OrderOutcome = 'filled' | 'working' | 'failed' | 'other'

export function orderOutcome(status: string): OrderOutcome {
    if (status === 'TRADED') return 'filled'
    if ((OPEN_ORDER_STATUSES as readonly string[]).includes(status)) return 'working'
    if ((FAILED_ORDER_STATUSES as readonly string[]).includes(status)) return 'failed'
    return 'other'
}

/** Venue strings arrive as `NSE_EQ` / `NSE_FNO`; render them readably. */
export function formatSegment(segment: string) {
    return segment?.replaceAll('_', ' · ') || '—'
}
