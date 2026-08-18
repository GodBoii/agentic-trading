'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/ui/empty-state'
import { Refresh } from '@/components/ui/icons'
import { Notice } from '@/components/ui/notice'
import { CellGrid, Panel } from '@/components/ui/panel'
import { Skeleton, SkeletonRows } from '@/components/ui/skeleton'
import { Spinner } from '@/components/ui/spinner'
import { StatTile } from '@/components/ui/stat'
import { SegmentedTabs, type TabItem } from '@/components/ui/tabs'
import { IconSwap } from '@/components/motion/icon-swap'
import { SkeletonReveal } from '@/components/motion/skeleton-reveal'
import { ViewSlide } from '@/components/motion/view-slide'
import { compactMoney, directionOf, formatClock, money, percent, signedMoney } from '@/lib/format'
import { AllocationPanel, CapitalPanel, OrderFlowPanel, PositionPnlPanel } from './insight-panels'
import { HoldingsTable, OrdersTable, PositionsTable } from './portfolio-tables'
import { usePortfolio } from './use-portfolio'

type Tab = 'holdings' | 'positions' | 'orders'

const PANEL_ID = 'portfolio-records'

/** Tab order, so the panel slide can derive its travel direction. */
const TAB_ORDER: Tab[] = ['holdings', 'positions', 'orders']

/**
 * The Portfolio screen's data body.
 *
 * Motion, in the order a visitor experiences it:
 *
 *   1. First load cross-fades from a shaped placeholder to the real figures
 *      (recipe 14) instead of the previous early `return` swapping one tree for
 *      another in a single frame. This is the most-seen transition in the app —
 *      it happens on every visit — and a hard cut here was the single roughest
 *      moment on the screen.
 *
 *   2. Each figure re-enters on change (recipe 02, inside `StatTile`). Five
 *      broker feeds refresh together, so without it a number quietly becoming a
 *      different number is invisible.
 *
 *   3. A background refresh dims the stale figures rather than replacing them
 *      with a spinner. The previous values stay readable and comparable while
 *      the new ones are in flight, which is what a trader actually wants; a
 *      spinner would withhold the data to announce that data is coming.
 *
 *   4. The refresh control cross-fades its icon into a spinner (recipe 09)
 *      rather than spinning the refresh glyph itself, and its label swaps in
 *      place (recipe 04).
 *
 *   5. The record tabs slide their active pill (recipe 16), and switching
 *      between Holdings / Positions / Orders slides the tables past each other
 *      (recipe 08) so the change of view is directional.
 */
export default function PortfolioOverview() {
    const { funds, holdings, positions, orders, loading, refreshing, error, updatedAt, analytics, reload } =
        usePortfolio()
    const [tab, setTab] = useState<Tab>('holdings')

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
                        <Button variant="subtle" onClick={() => void reload(true)} disabled={refreshing} swapLabel>
                            {refreshing ? 'Retrying' : 'Try again'}
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
        <SkeletonReveal loading={loading} skeleton={<PortfolioSkeleton />} label="Loading portfolio" flow>
            <section aria-label="Portfolio data" className="space-y-4">
                <div className="flex items-center justify-between gap-4">
                    <p className="text-[11px] text-ink-tertiary">
                        {updatedAt ? (
                            <>
                                Live broker data · updated{' '}
                                <span className="nums font-mono text-ink-secondary">
                                    {formatClock(updatedAt.toISOString())}
                                </span>
                            </>
                        ) : (
                            'Live broker data'
                        )}
                    </p>
                    <Button
                        size="sm"
                        onClick={() => void reload(true)}
                        disabled={refreshing}
                        aria-label="Refresh portfolio"
                        swapLabel
                    >
                        <IconSwap
                            showB={refreshing}
                            a={<Refresh size={13} />}
                            b={<Spinner size={13} />}
                            className="flex-shrink-0"
                        />
                        {refreshing ? 'Refreshing' : 'Refresh'}
                    </Button>
                </div>

                {error && !error.fatal && (
                    <Notice
                        tone="warning"
                        action={
                            <Button size="sm" variant="subtle" onClick={() => void reload(true)} disabled={refreshing} swapLabel>
                                {refreshing ? 'Retrying' : 'Retry'}
                            </Button>
                        }
                    >
                        {error.message}
                    </Notice>
                )}

                {/* Dimmed, not replaced, while a background refresh is in
                    flight — the figures below stay legible and comparable. */}
                <div className="t-stale space-y-4" data-stale={refreshing}>
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
                            meter={
                                funds
                                    ? { value: analytics.marginUse, tone: analytics.marginUse > 80 ? 'negative' : 'warning' }
                                    : undefined
                            }
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
                </div>

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
                        <ViewSlide index={TAB_ORDER.indexOf(tab)}>
                            {tab === 'holdings' && <HoldingsTable rows={holdings} />}
                            {tab === 'positions' && <PositionsTable rows={positions} />}
                            {tab === 'orders' && <OrdersTable rows={orders} />}
                        </ViewSlide>
                    </div>
                </Panel>
            </section>
        </SkeletonReveal>
    )
}

/** Mirrors the real layout so nothing shifts when data arrives. */
function PortfolioSkeleton() {
    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between">
                <Skeleton className="h-3 w-48" />
                <Skeleton className="h-7 w-24" delay={40} />
            </div>
            <CellGrid className="grid-cols-2 lg:grid-cols-5">
                {[0, 1, 2, 3, 4].map((item) => (
                    <div key={item} className="p-4 sm:p-5">
                        <Skeleton className="h-2.5 w-20" delay={item * 40} />
                        <Skeleton className="mt-4 h-5 w-28" delay={item * 40} />
                        <Skeleton className="mt-3 h-2 w-16" delay={item * 40} />
                    </div>
                ))}
            </CellGrid>
            <div className="grid gap-4 lg:grid-cols-2">
                {[0, 1].map((item) => (
                    <Panel key={item}>
                        <div className="panel-header">
                            <Skeleton className="h-3 w-40" delay={item * 40} />
                        </div>
                        <div className="panel-body space-y-3">
                            <Skeleton className="h-2 w-full rounded-full" delay={item * 40} />
                            {[0, 1, 2, 3].map((row) => (
                                <Skeleton key={row} className="h-2.5 w-full" delay={(row + item) * 40} />
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
