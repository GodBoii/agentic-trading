'use client'
import { useState } from 'react'
import ProductHeader from '@/components/product-header'
import { LiveRunBoard } from '@/components/agent/live-run-board'
import { reduceLiveRuns } from '@/lib/live-agent-runs'
import { TradeArchive } from '@/components/trades/trade-archive'
import { CellGrid, Panel, PanelBody, PanelHeader } from '@/components/ui/panel'
import { StatTile } from '@/components/ui/stat'
import { DivergingBars } from '@/components/charts/diverging-bars'
import { OrdersTable } from '@/components/dashboard/portfolio-tables'
import '@/app/dashboard/dashboard.css'

const stocks = ['RACL Geartech', 'Shree Oswal Seeds And Chemicals', 'Quadrant Future Tek', 'Sika Interplant Systems', 'Awfis Space Solutions']
const initial = stocks.reduce((runs, name, index) => reduceLiveRuns(runs, {
    type: index === 3 ? 'stock_agent_failed' : index === 4 ? 'stock_agent_completed' : 'stock_agent_thinking',
    request_id: `intra-finder-20260911-${index}`, rank: 1, sequence: 1, display_name: name,
    message: index === 3 ? 'Market data request timed out.' : 'Checking price action and available liquidity before evaluating this candidate.',
    sent_at_utc: `2026-09-11T09:0${index}:00Z`,
}), {})
export default function Preview() {
    const [view, setView] = useState('runs')
    const [runs, setRuns] = useState(initial)
    const [stream, setStream] = useState<'live' | 'reconnecting'>('live')
    return <div className="product-shell min-h-screen bg-canvas"><ProductHeader email="preview@example.test" />
        <main className="mx-auto max-w-[1320px] px-4 py-6 sm:px-6 lg:px-8">
            <div className="mb-6 flex flex-wrap gap-3 text-sm"><span>Local synthetic preview</span>{['runs','portfolio','trades'].map((v) => <button className="run-filter" key={v} onClick={() => setView(v)}>{v}</button>)}<button onClick={() => setRuns(reduceLiveRuns(runs, { type: 'stock_agent_started', request_id: `new-${Object.keys(runs).length}`, rank: 1, display_name: 'New concurrent candidate', sent_at_utc: '2026-09-11T09:20:00Z' }))}>Add parallel run</button><button onClick={() => setStream(stream === 'live' ? 'reconnecting' : 'live')}>Toggle connection</button></div>
            <header className="mb-6"><p className="dash-label">Autonomous execution</p><h1 className="section-title">{view === 'runs' ? 'Agent' : view === 'portfolio' ? 'Portfolio' : 'Trades'}</h1></header>
            {view === 'runs' && <LiveRunBoard runs={runs} stream={stream} />}
            {view === 'trades' && <TradeArchive sessions={stocks.map((title,index) => ({session_id:String(index),request_id:String(index),title,status:'completed',created_at_utc:`2026-09-11T09:0${index}:00Z`,agent_count:1}))} loading={false} error={null} openingId={null} onOpen={() => setView('runs')} onPrefetch={() => {}} onRetry={() => {}} />}
            {view === 'portfolio' && <div className="space-y-6"><CellGrid className="grid-cols-2 lg:grid-cols-4"><StatTile label="Available balance" value="₹2,206"/><StatTile label="Day P&L" value="+₹25"/><StatTile label="Exposure" value="₹0"/><StatTile label="Margin utilized" value="₹8"/></CellGrid>
                <Panel><PanelHeader title="Profit and loss by position"/><PanelBody><DivergingBars items={stocks.map((label,index) => ({key:String(index),label,value:18-index*7,meta:'0 net · INTRADAY'}))} formatValue={(v) => `${v > 0 ? '+' : ''}₹${v}`} /></PanelBody></Panel>
                <Panel><PanelHeader title="Orders"/><OrdersTable rows={stocks.map((tradingSymbol,index) => ({ orderId:String(index),orderStatus:'TRADED',transactionType:'BUY',exchangeSegment:'NSE_EQ',productType:'INTRADAY',orderType:'LIMIT',tradingSymbol,securityId:String(index),quantity:4,price:250.55,averageTradedPrice:250.55,filledQty:4,createTime:'2026-09-11T09:20:00Z' }))} /></Panel>
            </div>}
        </main></div>
}
