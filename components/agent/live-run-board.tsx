'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import type { LiveRun } from '@/lib/live-agent-runs'
import type { StreamState } from '@/components/ai-trading/types'
import { agentDisplayName, coalesceAgentEvents, eventTitle } from '@/components/ai-trading/utils'
import { formatTime } from '@/lib/format'
import { Badge } from '@/components/ui/badge'
import { AgentWorkspace } from './agent-workspace'
import { StreamIndicator, streamHint } from './stream-indicator'
import { ArrowLeft, ChevronRight } from '@/components/ui/icons'
import type { AgentSlot } from './agent-roster'

type Filter = 'all' | 'running' | 'failed' | 'finished'

export function LiveRunBoard({ runs, stream }: { runs: Record<string, LiveRun>; stream: StreamState }) {
    const [filter, setFilter] = useState<Filter>('all')
    const [query, setQuery] = useState('')
    const [selectedKey, setSelectedKey] = useState<string | null>(null)
    const backButton = useRef<HTMLButtonElement>(null)
    const selectionButton = useRef<HTMLButtonElement | null>(null)
    useEffect(() => {
        if (selectedKey && window.matchMedia('(max-width: 767px)').matches) backButton.current?.focus()
    }, [selectedKey])
    const rows = useMemo(() => Object.values(runs).flatMap((run) => Object.entries(run.events).map(([rank, raw]) => {
        const events = coalesceAgentEvents(raw)
        const named = [...events].reverse().find((event) => event.display_name || event.symbol)
        const completed = events.some((event) => event.type === 'stock_agent_completed')
        const noTrade = events.some((event) => event.type === 'stock_agent_no_trade')
        const failed = events.some((event) => event.type === 'stock_agent_failed') || (!completed && !noTrade && run.finishedState === 'failed')
        const complete = completed || noTrade || run.finishedState === 'completed'
        const slot: AgentSlot = { rank: Number(rank), name: agentDisplayName(named), events, complete, failed }
        return { key: `${run.id}:${rank}`, run, slot, state: failed ? 'failed' : complete ? 'finished' : 'running' }
    })).sort((a, b) => Number(b.state === 'running') - Number(a.state === 'running') ||
        (b.run.updatedAt || '').localeCompare(a.run.updatedAt || '')), [runs])
    const visible = rows.filter((row) => (filter === 'all' || row.state === filter) &&
        `${row.slot.name} ${row.run.id}`.toLowerCase().includes(query.trim().toLowerCase()))
    const selected = rows.find((row) => row.key === selectedKey)
    const runningCount = rows.filter((row) => row.state === 'running').length

    const degraded = stream !== 'live' && stream !== 'connecting' && stream !== 'paused'

    return (
        <section aria-label="Live agent runs" className="live-runs">
            <header className="run-board-heading">
                <div className="min-w-0">
                    <h2 className="text-lg font-medium tracking-[-0.015em]">Agent runs</h2>
                    <p className="mt-0.5 text-sm text-ink-secondary">
                        <span className="nums">{runningCount}</span> active · <span className="nums">{rows.length}</span> seen this session
                    </p>
                </div>
                <StreamIndicator state={stream} />
            </header>
            {/* Same wording as the chip's tooltip, so the two never disagree
                about what state the stream is in. */}
            {degraded && (
                <p className="mb-4 text-sm text-ink-secondary" role="status">
                    {streamHint(stream)} Activity below may be behind.
                </p>
            )}
            <div className="run-filters">
                <div className="run-filter-rail no-scrollbar" role="group" aria-label="Filter runs">
                    {(['all', 'running', 'failed', 'finished'] satisfies Filter[]).map((value) => (
                        <button key={value} type="button" aria-pressed={filter === value} onClick={() => setFilter(value)} className="run-filter">
                            {value === 'all' ? 'All' : value === 'running' ? 'Active' : value === 'failed' ? 'Failed' : 'Finished'}
                            <span className="run-filter-count nums">{value === 'all' ? rows.length : rows.filter((row) => row.state === value).length}</span>
                        </button>
                    ))}
                </div>
                <input type="search" aria-label="Search runs by stock or request" placeholder="Search stock or request" value={query} onChange={(event) => setQuery(event.target.value)} className="run-search" />
            </div>
            <div className="run-split" data-detail={Boolean(selected)}>
                <aside className="run-list" aria-label="Choose an agent run">
                    {visible.length ? <ul>{visible.map((row) => {
                        const latest = row.slot.events[row.slot.events.length - 1]
                        return <li key={row.key}>
                            <button type="button" className="run-row" aria-pressed={selectedKey === row.key} onClick={(event) => { selectionButton.current = event.currentTarget; setSelectedKey(row.key) }}>
                                <span className="flex items-center justify-between gap-3"><span className="min-w-0 flex-1 font-medium break-words">{row.slot.name}</span>
                                    <Badge className="shrink-0" tone={row.state === 'failed' ? 'negative' : row.state === 'running' ? 'warning' : 'neutral'}>{row.state === 'running' ? 'Active' : row.state === 'failed' ? 'Failed' : 'Finished'}</Badge></span>
                                <span className="mt-2 block truncate text-xs text-ink-secondary">{latest ? eventTitle(latest) : 'Queued'}</span>
                                <span className="mt-2 flex justify-between gap-3 text-xs text-ink-tertiary"><span className="truncate">{row.run.id}</span><time className="shrink-0 nums">{formatTime(row.run.updatedAt)}</time></span>
                            </button>
                        </li>
                    })}</ul> : <div className="px-4 py-10"><h3 className="text-[15px] font-medium">{rows.length ? 'No matching runs' : 'No runs yet this session'}</h3><p className="mt-1.5 max-w-sm text-sm text-ink-secondary">{rows.length ? 'Try another stock or filter.' : 'When the scanner picks a stock, its agent shows up here and streams what it reads and decides.'}</p></div>}
                    <Link href="/dashboard/trades" className="run-archive-link t-press">Archived runs<ChevronRight size={14} /></Link>
                </aside>
                <div className="run-detail">
                    {selected ? <>
                        <button ref={backButton} type="button" className="run-back" onClick={() => { setSelectedKey(null); requestAnimationFrame(() => selectionButton.current?.focus()) }}><ArrowLeft size={16} />All runs</button>
                        <p className="mb-3 break-all font-mono text-xs text-ink-tertiary">Request {selected.run.id}</p>
                        <AgentWorkspace key={selected.key} slot={selected.slot} />
                    </> : <div className="py-12 text-center"><h3 className="font-medium">{rows.length ? 'Select a run to follow its activity' : 'Ready for the next candidate'}</h3><p className="mx-auto mt-2 max-w-sm text-sm text-ink-secondary">Decisions, tool calls and charts stay together for each agent.</p></div>}
                </div>
            </div>
        </section>
    )
}
