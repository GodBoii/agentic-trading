'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'

type Funds = {
    dhanClientId: string
    availabelBalance: number
    sodLimit: number
    collateralAmount: number
    receiveableAmount: number
    utilizedAmount: number
    withdrawableBalance: number
}

type Holding = {
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

type Position = {
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

type Order = {
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

type Tab = 'holdings' | 'positions' | 'orders'

const money = (value = 0) => new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
}).format(value)

const compactMoney = (value = 0) => new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    notation: 'compact',
    maximumFractionDigits: 2,
}).format(value)

async function readApi<T>(url: string): Promise<T> {
    const response = await fetch(url, { cache: 'no-store' })
    const payload = await response.json().catch(() => null)
    if (!response.ok) throw new Error(payload?.error || 'Unable to load Dhan data')
    return payload as T
}

export default function PortfolioOverview() {
    const [funds, setFunds] = useState<Funds | null>(null)
    const [holdings, setHoldings] = useState<Holding[]>([])
    const [positions, setPositions] = useState<Position[]>([])
    const [orders, setOrders] = useState<Order[]>([])
    const [tab, setTab] = useState<Tab>('holdings')
    const [loading, setLoading] = useState(true)
    const [refreshing, setRefreshing] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [updatedAt, setUpdatedAt] = useState<Date | null>(null)

    const load = useCallback(async (background = false) => {
        background ? setRefreshing(true) : setLoading(true)
        setError(null)
        const results = await Promise.allSettled([
            readApi<Funds>('/api/dhan/funds'),
            readApi<Holding[]>('/api/dhan/holdings'),
            readApi<Position[]>('/api/dhan/positions'),
            readApi<Order[]>('/api/dhan/orders'),
        ])

        if (results[0].status === 'fulfilled') setFunds(results[0].value)
        if (results[1].status === 'fulfilled') setHoldings(Array.isArray(results[1].value) ? results[1].value : [])
        if (results[2].status === 'fulfilled') setPositions(Array.isArray(results[2].value) ? results[2].value : [])
        if (results[3].status === 'fulfilled') setOrders(Array.isArray(results[3].value) ? results[3].value : [])

        const failures = results.filter((result) => result.status === 'rejected') as PromiseRejectedResult[]
        if (failures.length === results.length) {
            setError(failures[0].reason instanceof Error ? failures[0].reason.message : 'Connect Dhan to view your portfolio')
        } else if (failures.length) {
            setError('Some Dhan data could not be refreshed. Showing the latest available values.')
        }

        if (failures.length < results.length) setUpdatedAt(new Date())
        setLoading(false)
        setRefreshing(false)
    }, [])

    useEffect(() => {
        load()
    }, [load])

    useEffect(() => {
        const handleConnectionChange = (event: Event) => {
            const change = event as CustomEvent<{ connected?: boolean }>
            if (change.detail?.connected !== false) return

            setFunds(null)
            setHoldings([])
            setPositions([])
            setOrders([])
            setUpdatedAt(null)
            setError('Connect Dhan to view your live portfolio.')
        }

        window.addEventListener('dhan-connection-change', handleConnectionChange)
        return () => window.removeEventListener('dhan-connection-change', handleConnectionChange)
    }, [])

    const analytics = useMemo(() => {
        const invested = holdings.reduce((sum, item) => sum + item.totalQty * item.avgCostPrice, 0)
        const realized = positions.reduce((sum, item) => sum + item.realizedProfit, 0)
        const unrealized = positions.reduce((sum, item) => sum + item.unrealizedProfit, 0)
        const exposure = positions.reduce((sum, item) => {
            const referencePrice = item.netQty >= 0 ? item.buyAvg : item.sellAvg
            return sum + Math.abs(item.netQty * referencePrice)
        }, 0)
        const tradedOrders = orders.filter((item) => item.orderStatus === 'TRADED').length
        const openOrders = orders.filter((item) => ['PENDING', 'TRANSIT', 'PART_TRADED'].includes(item.orderStatus)).length
        const marginUse = funds?.sodLimit ? Math.min(100, Math.max(0, (funds.utilizedAmount / funds.sodLimit) * 100)) : 0
        return { invested, realized, unrealized, dayPnl: realized + unrealized, exposure, tradedOrders, openOrders, marginUse }
    }, [funds, holdings, positions, orders])

    const tabs: { id: Tab; label: string; count: number }[] = [
        { id: 'holdings', label: 'Holdings', count: holdings.length },
        { id: 'positions', label: 'Positions', count: positions.filter((item) => item.positionType !== 'CLOSED').length },
        { id: 'orders', label: 'Orders', count: orders.length },
    ]

    if (loading) {
        return (
            <div className="space-y-4" aria-label="Loading portfolio data">
                <div className="grid animate-pulse grid-cols-2 gap-px overflow-hidden rounded-2xl border border-[var(--dash-border)] bg-[var(--dash-border)] lg:grid-cols-5">
                    {[0, 1, 2, 3, 4].map((item) => <div key={item} className="h-28 bg-[#0d0f12]" />)}
                </div>
                <div className="h-[420px] animate-pulse rounded-2xl border border-[var(--dash-border)] bg-white/[0.018]" />
            </div>
        )
    }

    return (
        <section aria-labelledby="portfolio-heading" className="space-y-4">
            <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                    <p className="dash-label mb-1.5">Dhan portfolio</p>
                    <h2 id="portfolio-heading" className="text-[21px] font-medium tracking-[-0.035em] text-[var(--dash-text)]">
                        Account overview
                    </h2>
                </div>
                <div className="flex items-center gap-3">
                    {updatedAt && (
                        <span className="hidden text-[10px] text-[var(--dash-text-muted)] sm:inline">
                            Updated {updatedAt.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}
                        </span>
                    )}
                    <button
                        type="button"
                        onClick={() => load(true)}
                        disabled={refreshing}
                        className="dash-btn !rounded-lg !px-3 !py-1.5 !text-[11px]"
                    >
                        <span className={refreshing ? 'inline-block animate-spin' : ''}>↻</span>
                        {refreshing ? 'Refreshing' : 'Refresh'}
                    </button>
                </div>
            </div>

            {error && (
                <div className={`rounded-xl border px-4 py-3 text-[12px] ${
                    funds ? 'border-[var(--dash-warning)]/20 bg-[var(--dash-warning)]/[0.04] text-[var(--dash-warning)]'
                        : 'border-[var(--dash-border)] bg-white/[0.02] text-[var(--dash-text-secondary)]'
                }`}>
                    {error}
                </div>
            )}

            <div className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-[var(--dash-border)] bg-[var(--dash-border)] lg:grid-cols-5">
                <Metric label="Available balance" value={funds ? money(funds.availabelBalance) : '—'} primary />
                <Metric label="Invested value" value={funds ? money(analytics.invested) : '—'} note={funds ? 'At average cost' : undefined} />
                <Metric label="Today's P&L" value={funds ? money(analytics.dayPnl) : '—'} tone={funds ? analytics.dayPnl : undefined} note={funds ? `${money(analytics.unrealized)} open` : undefined} />
                <Metric label="Withdrawable" value={funds ? money(funds.withdrawableBalance) : '—'} />
                <div className="col-span-2 bg-[#0d0f12] p-5 lg:col-span-1">
                    <div className="flex items-start justify-between">
                        <p className="dash-label">Margin used</p>
                        <p className="font-mono text-[11px] text-[var(--dash-text-secondary)]">{analytics.marginUse.toFixed(1)}%</p>
                    </div>
                    <p className="mt-3 text-[18px] font-medium tracking-[-0.03em] text-[var(--dash-text)]">{funds ? money(funds.utilizedAmount) : '—'}</p>
                    <div className="mt-3 h-1 overflow-hidden rounded-full bg-white/[0.06]">
                        <div className="h-full rounded-full bg-[var(--dash-warning)]" style={{ width: `${analytics.marginUse}%` }} />
                    </div>
                </div>
            </div>

            <div className="min-h-[430px] overflow-hidden rounded-2xl border border-[var(--dash-border)] bg-[#0d0f12]">
                <div className="flex items-center justify-between border-b border-[var(--dash-border)] px-3 sm:px-5">
                    <div className="flex min-w-0 items-center gap-1 overflow-x-auto no-scrollbar" role="tablist" aria-label="Portfolio views">
                        {tabs.map((item) => (
                            <button
                                key={item.id}
                                type="button"
                                role="tab"
                                aria-selected={tab === item.id}
                                onClick={() => setTab(item.id)}
                                className={`relative flex h-14 items-center gap-2 whitespace-nowrap px-3 text-[12px] transition-colors sm:px-4 ${
                                    tab === item.id ? 'text-white' : 'text-[var(--dash-text-muted)] hover:text-[var(--dash-text-secondary)]'
                                }`}
                            >
                                {item.label}
                                <span className="font-mono text-[9px] text-[var(--dash-text-muted)]">{item.count}</span>
                                {tab === item.id && <motion.span layoutId="portfolio-tab" className="absolute inset-x-3 bottom-0 h-px bg-[#37d67a]" />}
                            </button>
                        ))}
                    </div>
                    <div className="hidden items-center gap-5 text-[10px] text-[var(--dash-text-muted)] lg:flex">
                        <span>Exposure {compactMoney(analytics.exposure)}</span>
                        <span>Open orders {analytics.openOrders}</span>
                        <span>Executed {analytics.tradedOrders}</span>
                    </div>
                </div>

                <AnimatePresence mode="wait">
                    <motion.div
                        key={tab}
                        initial={{ opacity: 0, y: 4 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -4 }}
                        transition={{ duration: 0.18 }}
                    >
                        {tab === 'holdings' && <HoldingsView rows={holdings} />}
                        {tab === 'positions' && <PositionsView rows={positions} />}
                        {tab === 'orders' && <OrdersView rows={orders} />}
                    </motion.div>
                </AnimatePresence>
            </div>
        </section>
    )
}

function Metric({ label, value, note, primary, tone }: { label: string; value: string; note?: string; primary?: boolean; tone?: number }) {
    const toneClass = tone === undefined ? 'text-[var(--dash-text)]' : tone >= 0 ? 'text-[var(--dash-positive)]' : 'text-[var(--dash-negative)]'
    return (
        <div className="bg-[#0d0f12] p-5">
            <p className="dash-label">{label}</p>
            <p className={`mt-3 font-medium tracking-[-0.035em] ${primary ? 'text-[22px]' : 'text-[18px]'} ${toneClass}`}>
                {value}
            </p>
            {note && <p className="mt-1 text-[9px] text-[var(--dash-text-muted)]">{note}</p>}
        </div>
    )
}

function EmptyState({ title, detail }: { title: string; detail: string }) {
    return (
        <div className="grid min-h-[350px] place-items-center px-6 text-center">
            <div>
                <div className="mx-auto mb-4 h-8 w-8 rounded-full border border-dashed border-white/15" />
                <p className="text-[13px] text-[var(--dash-text-secondary)]">{title}</p>
                <p className="mt-1 text-[11px] text-[var(--dash-text-muted)]">{detail}</p>
            </div>
        </div>
    )
}

function HoldingsView({ rows }: { rows: Holding[] }) {
    if (!rows.length) return <EmptyState title="No holdings yet" detail="Delivery holdings from Dhan will appear here." />
    return (
        <Table headers={['Instrument', 'Available', 'Average cost', 'Invested value', 'Settlement']}>
            {rows.map((row) => (
                <tr key={`${row.securityId}-${row.exchange}`} className="border-t border-[var(--dash-border)] first:border-0 hover:bg-white/[0.012]">
                    <Cell><Instrument symbol={row.tradingSymbol} meta={`${row.exchange} · ${row.securityId}`} /></Cell>
                    <Cell right><strong>{row.availableQty}</strong><small>of {row.totalQty}</small></Cell>
                    <Cell right>{money(row.avgCostPrice)}</Cell>
                    <Cell right><strong>{money(row.totalQty * row.avgCostPrice)}</strong></Cell>
                    <Cell right>
                        <span className={row.t1Qty > 0 ? 'text-[var(--dash-warning)]' : 'text-[var(--dash-text-muted)]'}>
                            {row.t1Qty > 0 ? `T1 · ${row.t1Qty}` : 'Settled'}
                        </span>
                    </Cell>
                </tr>
            ))}
        </Table>
    )
}

function PositionsView({ rows }: { rows: Position[] }) {
    if (!rows.length) return <EmptyState title="No positions today" detail="Open and carry-forward positions will appear here." />
    return (
        <Table headers={['Instrument', 'Side / product', 'Net quantity', 'Average price', 'Realized P&L', 'Open P&L']}>
            {rows.map((row) => {
                const referencePrice = row.netQty >= 0 ? row.buyAvg : row.sellAvg
                return (
                    <tr key={`${row.securityId}-${row.productType}`} className="border-t border-[var(--dash-border)] first:border-0 hover:bg-white/[0.012]">
                        <Cell><Instrument symbol={row.tradingSymbol} meta={row.exchangeSegment.replace('_', ' · ')} /></Cell>
                        <Cell><Status text={row.positionType} positive={row.positionType === 'LONG'} negative={row.positionType === 'SHORT'} /><small>{row.productType}</small></Cell>
                        <Cell right><strong>{row.netQty}</strong><small>B {row.buyQty} · S {row.sellQty}</small></Cell>
                        <Cell right>{money(referencePrice)}</Cell>
                        <Cell right tone={row.realizedProfit}>{money(row.realizedProfit)}</Cell>
                        <Cell right tone={row.unrealizedProfit}><strong>{money(row.unrealizedProfit)}</strong></Cell>
                    </tr>
                )
            })}
        </Table>
    )
}

function OrdersView({ rows }: { rows: Order[] }) {
    if (!rows.length) return <EmptyState title="No orders today" detail="Today’s Dhan order book will appear here." />
    return (
        <Table headers={['Instrument', 'Side / type', 'Quantity', 'Price', 'Status', 'Placed at']}>
            {rows.map((row) => {
                const isComplete = row.orderStatus === 'TRADED'
                const isFailed = ['REJECTED', 'CANCELLED', 'EXPIRED'].includes(row.orderStatus)
                return (
                    <tr key={row.orderId} className="border-t border-[var(--dash-border)] first:border-0 hover:bg-white/[0.012]">
                        <Cell><Instrument symbol={row.tradingSymbol || row.securityId} meta={row.exchangeSegment.replace('_', ' · ')} /></Cell>
                        <Cell><Status text={row.transactionType} positive={row.transactionType === 'BUY'} negative={row.transactionType === 'SELL'} /><small>{row.productType} · {row.orderType}</small></Cell>
                        <Cell right><strong>{row.filledQty}/{row.quantity}</strong><small>filled</small></Cell>
                        <Cell right>{money(row.averageTradedPrice || row.price)}</Cell>
                        <Cell right><Status text={row.orderStatus.replace('_', ' ')} positive={isComplete} negative={isFailed} /></Cell>
                        <Cell right>{row.createTime?.split(' ')[1] || '—'}<small>{row.orderId.slice(-6)}</small></Cell>
                    </tr>
                )
            })}
        </Table>
    )
}

function Table({ headers, children }: { headers: string[]; children: React.ReactNode }) {
    return (
        <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] border-collapse">
                <thead>
                    <tr className="border-b border-[var(--dash-border)]">
                        {headers.map((header, index) => (
                            <th key={header} className={`px-5 py-3 font-normal dash-label ${index ? 'text-right' : 'text-left'}`}>{header}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>{children}</tbody>
            </table>
        </div>
    )
}

function Cell({ children, right, tone }: { children: React.ReactNode; right?: boolean; tone?: number }) {
    const toneClass = tone === undefined ? 'text-[var(--dash-text-secondary)]' : tone >= 0 ? 'text-[var(--dash-positive)]' : 'text-[var(--dash-negative)]'
    return (
        <td className={`px-5 py-4 font-mono text-[11px] ${right ? 'text-right' : 'text-left'} ${toneClass}`}>
            {children}
        </td>
    )
}

function Instrument({ symbol, meta }: { symbol: string; meta: string }) {
    return (
        <div>
            <p className="font-sans text-[12px] font-medium text-[var(--dash-text)]">{symbol}</p>
            <small className="mt-1 block font-mono text-[9px] text-[var(--dash-text-muted)]">{meta}</small>
        </div>
    )
}

function Status({ text, positive, negative }: { text: string; positive?: boolean; negative?: boolean }) {
    const className = positive
        ? 'border-[var(--dash-positive)]/20 bg-[var(--dash-positive)]/[0.06] text-[var(--dash-positive)]'
        : negative
            ? 'border-[var(--dash-negative)]/20 bg-[var(--dash-negative)]/[0.06] text-[var(--dash-negative)]'
            : 'border-white/[0.07] bg-white/[0.03] text-[var(--dash-text-secondary)]'
    return <span className={`inline-flex rounded-md border px-1.5 py-0.5 font-mono text-[8px] font-medium tracking-wide ${className}`}>{text}</span>
}
