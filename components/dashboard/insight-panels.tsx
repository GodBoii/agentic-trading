'use client'

import { CompositionBar } from '@/components/charts/composition-bar'
import { DivergingBars } from '@/components/charts/diverging-bars'
import { OrderFlowTimeline } from '@/components/charts/order-flow-timeline'
import { StatusDot } from '@/components/ui/badge'
import { Panel, PanelBody, PanelFooter, PanelHeader } from '@/components/ui/panel'
import { compactMoney, count, money, percent, signedMoney } from '@/lib/format'
import type { PortfolioState } from './use-portfolio'

/** Where the account's money currently sits, and how much of the limit is live. */
export function CapitalPanel({ funds, analytics }: Pick<PortfolioState, 'funds' | 'analytics'>) {
    return (
        <Panel aria-labelledby="capital-title">
            <PanelHeader
                titleId="capital-title"
                label="Funds"
                // "Fund deployment", not "Capital deployment": the Agent screen
                // owns "Capital per trade", and two panels using "capital" for
                // unrelated things is how a reader conflates a balance breakdown
                // with a per-trade limit.
                title="Fund deployment"
                actions={
                    <span className="nums font-mono text-[11px] text-ink-secondary">
                        {percent(analytics.marginUse)} of limit
                    </span>
                }
            />
            <PanelBody>
                <CompositionBar
                    segments={analytics.capitalSegments}
                    formatValue={money}
                    legendColumns={1}
                    emptyLabel="Fund limits are unavailable for this account."
                />
            </PanelBody>
            {funds && (
                <PanelFooter>
                    <dl className="flex flex-wrap gap-x-6 gap-y-1 text-[10px] text-ink-tertiary">
                        <div className="flex gap-1.5">
                            <dt>Start-of-day limit</dt>
                            <dd className="nums font-mono text-ink-secondary">{money(funds.sodLimit)}</dd>
                        </div>
                        <div className="flex gap-1.5">
                            <dt>Withdrawable</dt>
                            <dd className="nums font-mono text-ink-secondary">{money(funds.withdrawableBalance)}</dd>
                        </div>
                    </dl>
                </PanelFooter>
            )}
        </Panel>
    )
}

/**
 * Concentration risk. Explicitly labelled "at cost" because the broker payload
 * has no last-traded price — presenting these weights as current market
 * exposure would be a guess dressed as data.
 */
export function AllocationPanel({ holdings, analytics }: Pick<PortfolioState, 'holdings' | 'analytics'>) {
    const segments = analytics.allocationSegments
    const total = segments.reduce((sum, segment) => sum + segment.value, 0)
    const largest = segments[0]

    return (
        <Panel aria-labelledby="allocation-title">
            <PanelHeader
                titleId="allocation-title"
                label="Holdings"
                title="Concentration by invested value"
                description="Weights are calculated at average cost, not live market value."
                actions={
                    <span className="nums font-mono text-[11px] text-ink-secondary">
                        {count(holdings.length)} {holdings.length === 1 ? 'name' : 'names'}
                    </span>
                }
            />
            <PanelBody>
                <CompositionBar
                    segments={segments}
                    formatValue={money}
                    legendColumns={1}
                    emptyLabel="No delivery holdings to allocate."
                />
            </PanelBody>
            {largest && total > 0 && (
                <PanelFooter>
                    <p className="text-[10px] text-ink-tertiary">
                        Largest position{' '}
                        <span className="text-ink-secondary">{largest.label}</span> at{' '}
                        <span className="nums font-mono text-ink-secondary">
                            {percent((largest.value / total) * 100)}
                        </span>{' '}
                        of {money(total)} invested.
                    </p>
                </PanelFooter>
            )}
        </Panel>
    )
}

/** Signed P&L per position, ranked, so winners and losers are comparable. */
export function PositionPnlPanel({ analytics }: Pick<PortfolioState, 'analytics'>) {
    const { positionPnl, realized, unrealized } = analytics
    return (
        <Panel aria-labelledby="pnl-title">
            <PanelHeader
                titleId="pnl-title"
                label="Positions"
                title="Profit and loss by position"
                actions={
                    <span className="nums font-mono text-[11px] text-ink-secondary">
                        {signedMoney(realized + unrealized)}
                    </span>
                }
            />
            <PanelBody>
                <DivergingBars items={positionPnl} formatValue={signedMoney} />
            </PanelBody>
            <PanelFooter>
                <dl className="flex flex-wrap gap-x-6 gap-y-1 text-[10px] text-ink-tertiary">
                    <div className="flex gap-1.5">
                        <dt>Realized</dt>
                        <dd className="nums font-mono text-ink-secondary">{signedMoney(realized)}</dd>
                    </div>
                    <div className="flex gap-1.5">
                        <dt>Open</dt>
                        <dd className="nums font-mono text-ink-secondary">{signedMoney(unrealized)}</dd>
                    </div>
                </dl>
            </PanelFooter>
        </Panel>
    )
}

/**
 * Intraday order timing. The footer doubles as the chart legend, so the marker
 * colours are decodable without a separate key.
 */
export function OrderFlowPanel({ orders, analytics }: Pick<PortfolioState, 'orders' | 'analytics'>) {
    return (
        <Panel aria-labelledby="flow-title">
            <PanelHeader
                titleId="flow-title"
                label="Order flow"
                title="When today's orders were placed"
                actions={
                    <span className="nums font-mono text-[11px] text-ink-secondary">
                        {percent(analytics.fillRate, 0)} filled
                    </span>
                }
            />
            <PanelBody>
                <OrderFlowTimeline points={analytics.orderPoints} />
            </PanelBody>
            <PanelFooter>
                <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
                    <LegendCount tone="positive" label="Filled" value={analytics.filledOrders.length} />
                    <LegendCount tone="warning" label="Working" value={analytics.workingOrders.length} />
                    <LegendCount tone="negative" label="Rejected" value={analytics.failedOrders.length} />
                    <span className="ml-auto text-[10px] text-ink-tertiary">
                        {count(orders.length)} orders · {compactMoney(analytics.exposure)} exposure
                    </span>
                </div>
            </PanelFooter>
        </Panel>
    )
}

function LegendCount({
    tone,
    label,
    value,
}: {
    tone: 'positive' | 'warning' | 'negative'
    label: string
    value: number
}) {
    return (
        <span className="flex items-center gap-2 text-[10px] text-ink-tertiary">
            <StatusDot tone={tone} />
            {label}
            <span className="nums font-mono text-ink-secondary">{value}</span>
        </span>
    )
}
