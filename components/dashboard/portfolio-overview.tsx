'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/ui/empty-state'
import { Refresh } from '@/components/ui/icons'
import { Notice } from '@/components/ui/notice'
import { CellGrid, Panel } from '@/components/ui/panel'
import { Skeleton, SkeletonRows } from '@/components/ui/skeleton'
import { StatTile } from '@/components/ui/stat'
import { SegmentedTabs, type TabItem } from '@/components/ui/tabs'
import { cn } from '@/lib/cn'
import { compactMoney, directionOf, formatClock, money, percent, signedMoney } from '@/lib/format'
import { AllocationPanel, CapitalPanel, OrderFlowPanel, PositionPnlPanel } from './insight-panels'
import { HoldingsTable, OrdersTable, PositionsTable } from './portfolio-tables'
import { usePortfolio } from './use-portfolio'

type Tab = 'holdings' | 'positions' | 'orders'

const PANEL_ID = 'portfolio-records'

export default function PortfolioOverview() {
    const portfolio = usePortfolio()
    const { funds, holdings, positions, orders, loading, refreshing, error, updatedAt, analytics, reload } = portfolio
    const [tab, setTab] = useState<Tab>('holdings')

    if (loading) return <PortfolioSkeleton />

    // Nothing loaded at all — almost always an unconnected or expired broker
    // session. A wall of zeroed metrics would imply a funded empty account.
    if (error?.fatal) {
        return (
            <Panel>
                <EmptyState
                    title="Portfolio data unavailable"
                    detail={error.message}
                    minHeight={280}
                    action={
                        <Button variant="subtle" onClick={() => void reload(true)} disabled={refreshing}>
                            <Refresh size={14} className={refreshing ? 'animate-spin' : undefined} />
                            Try again
                        </Button>
                    }
                />
            </Panel>
        )
    }

    const tabs: TabItem<Tab>[] = [
        { id: 'holdings', label: 'Holdings', count: holdings.length },
        { id: 'positions', label: 'Positions', count: analytics.openPositions.length },
        { id: 'orders', label: 'Orders', count: orders.length },
    ]

    return (
        <section aria-label="Portfolio data" className="space-y-4">
            <div className="flex items-center justify-between gap-4">
                <p className="text-[11px] text-ink-tertiary">
                    {updatedAt ? (
                        <>
                            Live broker data · updated{' '}
                            <span className="nums font-mono text-ink-secondary">{formatClock(updatedAt.toISOString())}</span>
                        </>
                    ) : (
                        'Live broker data'
                    )}
                </p>
                <Button size="sm" onClick={() => void reload(true)} disabled={refreshing} aria-label="Refresh portfolio">
                    <Refresh size={13} className={cn(refreshing && 'animate-spin')} />
                    {refreshing ? 'Refreshing' : 'Refresh'}
                </Button>
            </div>

            {error && !error.fatal && (
                <Notice
                    tone="warning"
                    action={
                        <Button size="sm" variant="subtle" onClick={() => void reload(true)} disabled={refreshing}>
                            Retry
                        </Button>
                    }
                >
                    {error.message}
                </Notice>
            )}

            <CellGrid className="grid-cols-2 lg:grid-cols-5">
                <StatTile
                    label="Available balance"
                    value={funds ? money(funds.availabelBalance) : '—'}
                    note={funds ? `${money(funds.withdrawableBalance)} withdrawable` : undefined}
                    emphasis="primary"
                />
                <StatTile
                    label="Invested value"
                    value={holdings.length ? money(analytics.invested) : '—'}
                    note={holdings.length ? 'At average cost' : 'No holdings'}
                />
                <StatTile
                    label="Day P&L"
                    value={positions.length ? signedMoney(analytics.dayPnl) : '—'}
                    direction={positions.length ? directionOf(analytics.dayPnl) : 'neutral'}
                    note={
                        positions.length
                            ? `${signedMoney(analytics.unrealized)} open · ${signedMoney(analytics.realized)} booked`
                            : 'No positions today'
                    }
                />
                <StatTile
                    label="Exposure"
                    value={analytics.openPositions.length ? money(analytics.exposure) : '—'}
                    note={
                        analytics.openPositions.length
                            ? `${analytics.openPositions.length} open ${analytics.openPositions.length === 1 ? 'position' : 'positions'}`
                            : 'Nothing open'
                    }
                />
                <StatTile
                    label="Margin used"
                    value={funds ? money(funds.utilizedAmount) : '—'}
                    trailing={funds ? percent(analytics.marginUse) : undefined}
                    meter={funds ? { value: analytics.marginUse, tone: analytics.marginUse > 80 ? 'negative' : 'warning' } : undefined}
                    note={funds ? `of ${compactMoney(funds.sodLimit)} limit` : undefined}
                    className="col-span-2 lg:col-span-1"
                />
            </CellGrid>

            <div className="grid gap-4 lg:grid-cols-2">
                <CapitalPanel funds={funds} analytics={analytics} />
                <AllocationPanel holdings={holdings} analytics={analytics} />
            </div>

            {/* Rendered only when there is something to plot — an empty chart
                frame communicates nothing and costs a screenful. */}
            {analytics.positionPnl.length > 0 && <PositionPnlPanel analytics={analytics} />}
            {orders.length > 0 && <OrderFlowPanel orders={orders} analytics={analytics} />}

            <Panel>
                <div className="panel-header">
                    <SegmentedTabs
                        items={tabs}
                        value={tab}
                        onChange={setTab}
                        ariaLabel="Portfolio records"
                        panelId={PANEL_ID}
                    />
                    <p className="hidden text-[10px] text-ink-tertiary sm:block">
                        {tab === 'holdings' && 'Settled and pending delivery quantities'}
                        {tab === 'positions' && 'Realized and open profit per position'}
                        {tab === 'orders' && "Today's order book with fill progress"}
                    </p>
                </div>
                <div id={PANEL_ID} role="tabpanel" aria-labelledby={`tab-${tab}`}>
                    {tab === 'holdings' && <HoldingsTable rows={holdings} />}
                    {tab === 'positions' && <PositionsTable rows={positions} />}
                    {tab === 'orders' && <OrdersTable rows={orders} />}
                </div>
            </Panel>
        </section>
    )
}

/** Mirrors the real layout so nothing shifts when data arrives. */
function PortfolioSkeleton() {
    return (
        <div className="space-y-4" aria-busy="true" aria-label="Loading portfolio">
            <div className="flex items-center justify-between">
                <Skeleton className="h-3 w-48" />
                <Skeleton className="h-7 w-24" />
            </div>
            <CellGrid className="grid-cols-2 lg:grid-cols-5">
                {[0, 1, 2, 3, 4].map((item) => (
                    <div key={item} className="p-4 sm:p-5">
                        <Skeleton className="h-2.5 w-20" />
                        <Skeleton className="mt-4 h-5 w-28" />
                        <Skeleton className="mt-3 h-2 w-16" />
                    </div>
                ))}
            </CellGrid>
            <div className="grid gap-4 lg:grid-cols-2">
                {[0, 1].map((item) => (
                    <Panel key={item}>
                        <div className="panel-header">
                            <Skeleton className="h-3 w-40" />
                        </div>
                        <div className="panel-body space-y-3">
                            <Skeleton className="h-2 w-full rounded-full" />
                            {[0, 1, 2, 3].map((row) => (
                                <Skeleton key={row} className="h-2.5 w-full" />
                            ))}
                        </div>
                    </Panel>
                ))}
            </div>
            <Panel>
                <div className="panel-header">
                    <Skeleton className="h-7 w-64" />
                </div>
                <SkeletonRows rows={6} columns={5} />
            </Panel>
        </div>
    )
}
