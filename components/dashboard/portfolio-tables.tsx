'use client'

import { Badge, type Tone } from '@/components/ui/badge'
import { DataTable, Instrument, type Column } from '@/components/ui/data-table'
import { EmptyState } from '@/components/ui/empty-state'
import { Meter } from '@/components/ui/meter'
import { directionOf, formatClock, money, price } from '@/lib/format'
import { formatSegment, orderOutcome, type Holding, type Order, type Position } from './types'

const OUTCOME_TONE: Record<ReturnType<typeof orderOutcome>, Tone> = {
    filled: 'positive',
    working: 'warning',
    failed: 'negative',
    other: 'neutral',
}

export function HoldingsTable({ rows }: { rows: Holding[] }) {
    if (!rows.length) {
        return (
            <EmptyState
                title="No holdings"
                detail="Delivery holdings settled into your demat account will be listed here."
            />
        )
    }

    const columns: Column<Holding>[] = [
        {
            key: 'instrument',
            header: 'Instrument',
            render: (row) => <Instrument symbol={row.tradingSymbol} meta={`${row.exchange} · ${row.securityId}`} />,
        },
        {
            key: 'quantity',
            header: 'Quantity',
            align: 'right',
            render: (row) => (
                <>
                    <strong>{row.availableQty}</strong>
                    <small>of {row.totalQty} held</small>
                </>
            ),
        },
        {
            key: 'avgCost',
            header: 'Average cost',
            align: 'right',
            render: (row) => price(row.avgCostPrice),
        },
        {
            key: 'invested',
            header: 'Invested',
            align: 'right',
            render: (row) => <strong>{money(row.totalQty * row.avgCostPrice)}</strong>,
        },
        {
            key: 'pledged',
            header: 'Pledged',
            align: 'right',
            hideBelow: 'lg',
            render: (row) =>
                row.collateralQty > 0 ? (
                    <span className="text-warning">{row.collateralQty}</span>
                ) : (
                    <span className="text-ink-tertiary">—</span>
                ),
        },
        {
            key: 'settlement',
            header: 'Settlement',
            align: 'right',
            render: (row) =>
                row.t1Qty > 0 ? (
                    <Badge tone="warning">T1 · {row.t1Qty}</Badge>
                ) : (
                    <span className="text-ink-tertiary">Settled</span>
                ),
        },
    ]

    return (
        <DataTable
            columns={columns}
            rows={rows}
            rowKey={(row) => `${row.securityId}-${row.exchange}`}
            caption="Delivery holdings with quantity, average cost and settlement state"
            maxHeight={460}
        />
    )
}

export function PositionsTable({ rows }: { rows: Position[] }) {
    if (!rows.length) {
        return (
            <EmptyState
                title="No positions today"
                detail="Intraday and carry-forward positions appear here once the first order fills."
            />
        )
    }

    const columns: Column<Position>[] = [
        {
            key: 'instrument',
            header: 'Instrument',
            render: (row) => <Instrument symbol={row.tradingSymbol} meta={formatSegment(row.exchangeSegment)} />,
        },
        {
            key: 'side',
            header: 'Side',
            render: (row) => (
                <>
                    <Badge
                        tone={row.positionType === 'LONG' ? 'positive' : row.positionType === 'SHORT' ? 'negative' : 'neutral'}
                    >
                        {row.positionType}
                    </Badge>
                    <small>{row.productType}</small>
                </>
            ),
        },
        {
            key: 'netQty',
            header: 'Net qty',
            align: 'right',
            render: (row) => (
                <>
                    <strong>{row.netQty}</strong>
                    <small>
                        {row.buyQty} bought · {row.sellQty} sold
                    </small>
                </>
            ),
        },
        {
            key: 'avgPrice',
            header: 'Average price',
            align: 'right',
            hideBelow: 'sm',
            render: (row) => price(row.netQty >= 0 ? row.buyAvg : row.sellAvg),
        },
        {
            key: 'realized',
            header: 'Realized',
            align: 'right',
            hideBelow: 'md',
            direction: (row) => directionOf(row.realizedProfit),
            render: (row) => money(row.realizedProfit),
        },
        {
            key: 'unrealized',
            header: 'Open P&L',
            align: 'right',
            direction: (row) => directionOf(row.unrealizedProfit),
            render: (row) => <strong>{money(row.unrealizedProfit)}</strong>,
        },
    ]

    return (
        <DataTable
            columns={columns}
            rows={rows}
            rowKey={(row) => `${row.securityId}-${row.productType}`}
            caption="Open and closed positions with realized and unrealized profit"
            maxHeight={460}
        />
    )
}

export function OrdersTable({ rows }: { rows: Order[] }) {
    if (!rows.length) {
        return (
            <EmptyState
                title="No orders today"
                detail="Today's order book is empty. Orders placed manually or by the agent will appear here."
            />
        )
    }

    const columns: Column<Order>[] = [
        {
            key: 'instrument',
            header: 'Instrument',
            render: (row) => (
                <Instrument symbol={row.tradingSymbol || row.securityId} meta={formatSegment(row.exchangeSegment)} />
            ),
        },
        {
            key: 'side',
            header: 'Side',
            render: (row) => (
                <>
                    <Badge tone={row.transactionType === 'BUY' ? 'positive' : 'negative'}>{row.transactionType}</Badge>
                    <small>
                        {row.productType} · {row.orderType}
                    </small>
                </>
            ),
        },
        {
            key: 'fill',
            header: 'Filled',
            align: 'right',
            render: (row) => {
                const share = row.quantity > 0 ? (row.filledQty / row.quantity) * 100 : 0
                return (
                    <div className="ml-auto w-20">
                        <strong>
                            {row.filledQty}/{row.quantity}
                        </strong>
                        <Meter
                            className="mt-1.5"
                            value={share}
                            tone={share >= 100 ? 'positive' : share > 0 ? 'warning' : 'neutral'}
                            label={`${Math.round(share)}% filled`}
                        />
                    </div>
                )
            },
        },
        {
            key: 'price',
            header: 'Price',
            align: 'right',
            hideBelow: 'sm',
            render: (row) => price(row.averageTradedPrice || row.price),
        },
        {
            key: 'status',
            header: 'Status',
            align: 'right',
            render: (row) => (
                <>
                    <Badge tone={OUTCOME_TONE[orderOutcome(row.orderStatus)]}>
                        {row.orderStatus.replaceAll('_', ' ')}
                    </Badge>
                    {/* The broker's rejection reason was previously fetched but never shown.
                        Rendered as a span, not <small>: `.data-table td small` sets its own
                        colour in plain CSS and would override the danger tone. */}
                    {row.omsErrorDescription && (
                        <span className="mt-1 block max-w-[190px] whitespace-normal text-[9px] leading-snug text-negative/80">
                            {row.omsErrorDescription}
                        </span>
                    )}
                </>
            ),
        },
        {
            key: 'placed',
            header: 'Placed',
            align: 'right',
            hideBelow: 'md',
            render: (row) => (
                <>
                    {formatClock(row.createTime)}
                    <small>#{row.orderId.slice(-6)}</small>
                </>
            ),
        },
    ]

    return (
        <DataTable
            columns={columns}
            rows={rows}
            rowKey={(row) => row.orderId}
            caption="Today's order book with fill progress and status"
            maxHeight={460}
        />
    )
}
