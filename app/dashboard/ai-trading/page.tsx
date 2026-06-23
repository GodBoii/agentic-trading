'use client'

import { Suspense, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { motion } from 'framer-motion'

interface AgentStage {
    status: string
    generated_at_utc?: string | null
    summary?: Record<string, any> | null
    details?: Record<string, any> | null
}

interface AgentRunStatus {
    status: string
    current_stage: string
    updated_at_utc?: string
    message?: string | null
    error?: string | null
    request?: {
        request_id?: string
        requested_at_utc?: string
        email?: string | null
    }
    stages?: Record<string, AgentStage>
}

interface LiveAgentEvent {
    type: string
    rank?: number
    security_id?: number
    symbol?: string
    display_name?: string
    message?: string
    decision?: Record<string, any>
    attachments?: AgentAttachments
    agent_metadata?: Record<string, any>
    chart_count?: number
    report_text?: string
    error?: string
    sent_at_utc?: string
}

interface AgentImageCard {
    id?: string
    title?: string
    filename?: string
    path?: string
    url?: string
    cloud_url?: string | null
    storage_path?: string
    day_type?: string
    date?: string
    timeframe?: string
    candles?: number
}

interface AgentFileCard {
    id?: string
    title?: string
    filename?: string
    content_type?: string
    content?: string
    path?: string
    url?: string
    cloud_url?: string | null
    storage_path?: string
}

interface AgentAttachments {
    images?: AgentImageCard[]
    files?: AgentFileCard[]
}

interface AgentResult {
    rank?: number
    symbol?: string
    display_name?: string
    decision?: Record<string, any>
    attachments?: AgentAttachments
    agent_metadata?: Record<string, any> | null
    analysis?: string
    report_text?: string
}

interface TradeSessionSummary {
    session_id: string
    request_id: string
    title: string
    status: string
    created_at_utc?: string | null
    updated_at_utc?: string | null
    agent_count?: number
    executed_count?: number
    cloud_synced_at_utc?: string | null
    loaded_from_cloud?: boolean
}

interface TradeSession {
    session_id: string
    request_id?: string
    title: string
    status: string
    created_at_utc?: string | null
    updated_at_utc?: string | null
    request?: Record<string, any>
    summary?: Record<string, any> | null
    status_snapshot?: AgentRunStatus
    agents?: AgentResult[]
    cloud_synced_at_utc?: string | null
    loaded_from_cloud?: boolean
}

const stageLabels: Record<string, string> = {
    stage2: 'Stage 2 Momentum',
    stock_agent: 'Stock Agent',
}

const ease = [0.16, 1, 0.3, 1] as const

function formatTime(value?: string | null) {
    if (!value) return ''
    try {
        return new Intl.DateTimeFormat('en-IN', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
        }).format(new Date(value))
    } catch {
        return ''
    }
}

function formatDateTime(value?: string | null) {
    if (!value) return 'Unknown time'
    try {
        return new Intl.DateTimeFormat('en-IN', {
            dateStyle: 'medium',
            timeStyle: 'short',
        }).format(new Date(value))
    } catch {
        return 'Unknown time'
    }
}

function pluralize(count: number, singular: string, plural = `${singular}s`) {
    return `${count} ${count === 1 ? singular : plural}`
}

function statusText(stage: string, data?: AgentStage) {
    const status = data?.status || 'pending'
    if (stage === 'stage2' && status === 'running') {
        return 'Waiting for Stage 2 result from the sorting service.'
    }
    if (status === 'completed') return `${stageLabels[stage]} completed.`
    if (status === 'running') return `${stageLabels[stage]} is running now.`
    return `${stageLabels[stage]} is waiting.`
}

function stageBody(stage: string, data?: AgentStage) {
    if (!data || data.status !== 'completed') return null

    if (stage === 'stock_agent') {
        const results = data.details?.results || []
        return (
            <div className="space-y-3">
                <p className="text-[12px] text-ink-secondary font-mono">
                    Selected: {(data.summary?.selected_symbols || []).join(', ') || 'No symbols found'}
                </p>
                {results.map((result: any) => (
                    <div key={`${result.rank}-${result.symbol}`} className="pt-3 border-t border-line/60 first:border-t-0 first:pt-0">
                        <p className="text-success font-mono text-[10px] uppercase tracking-[0.18em]">
                            #{result.rank} {result.display_name || result.symbol}
                        </p>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-line rounded-lg overflow-hidden border border-line mt-3">
                            {Object.entries(result.decision || {}).slice(0, 8).map(([key, value]) => (
                                <div key={key} className="bg-[#08080a] p-3">
                                    <p className="text-[9px] text-ink-tertiary font-mono uppercase tracking-[0.15em]">
                                        {key.replaceAll('_', ' ')}
                                    </p>
                                    <p className="text-[12px] text-white font-mono font-medium break-words nums mt-1">
                                        {String(value)}
                                    </p>
                                </div>
                            ))}
                        </div>
                        <p className="text-[13px] text-ink-secondary mt-2 whitespace-pre-wrap leading-relaxed">
                            {result.report_text || result.analysis}
                        </p>
                    </div>
                ))}
            </div>
        )
    }

    const decision = data.details?.decision || {}
    return (
        <div className="space-y-3">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-line rounded-lg overflow-hidden border border-line">
                {Object.entries(decision).slice(0, 8).map(([key, value]) => (
                    <div key={key} className="bg-[#08080a] p-3">
                        <p className="text-[9px] text-ink-tertiary font-mono uppercase tracking-[0.15em]">
                            {key.replaceAll('_', ' ')}
                        </p>
                        <p className="text-[12px] text-white font-mono font-medium break-words nums mt-1">
                            {String(value)}
                        </p>
                    </div>
                ))}
            </div>
            <p className="text-[13px] text-ink-secondary whitespace-pre-wrap leading-relaxed">
                {data.details?.report_text}
            </p>
        </div>
    )
}

function websocketUrl() {
    if (typeof window === 'undefined') return null
    const configured = process.env.NEXT_PUBLIC_AI_TRADING_WS_URL
    const base = configured || `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.hostname}:8020/ai-trading/stream`
    const token = process.env.NEXT_PUBLIC_AI_TRADING_WS_TOKEN
    if (!token) return base
    const separator = base.includes('?') ? '&' : '?'
    return `${base}${separator}token=${encodeURIComponent(token)}`
}

function eventTitle(event: LiveAgentEvent) {
    if (event.type === 'stock_agent_started') return 'Started'
    if (event.type === 'stock_agent_charts_ready') return 'Charts Ready'
    if (event.type === 'stock_agent_completed') return 'Completed'
    if (event.type === 'stock_agent_failed') return 'Failed'
    if (event.type === 'stock_agent_selection') return 'Selected'
    return event.type.replaceAll('_', ' ')
}

function agentDisplayName(agent?: Partial<AgentResult | LiveAgentEvent> | null, fallback = 'Awaiting stock') {
    return agent?.display_name || agent?.symbol || fallback
}

function attachmentImageUrl(image: AgentImageCard) {
    return image.cloud_url || image.url || (image.path ? `/api/ai-trading/assets?path=${encodeURIComponent(String(image.path))}` : '')
}

function attachmentFileUrl(file: AgentFileCard) {
    return file.cloud_url || file.url || (file.path ? `/api/ai-trading/assets?path=${encodeURIComponent(String(file.path))}` : '')
}

function AttachmentStrip({ attachments }: { attachments?: AgentAttachments | null }) {
    const images = attachments?.images || []
    const files = attachments?.files || []
    if (!images.length && !files.length) return null

    return (
        <div className="space-y-4">
            {images.length > 0 && (
                <div className="overflow-x-auto no-scrollbar -mx-1 px-1">
                    <div className="flex gap-3 min-w-0 pb-1">
                        {images.map((image, index) => {
                            const src = attachmentImageUrl(image)
                            return (
                                <a
                                    key={`${image.id || image.filename || index}`}
                                    href={src}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="group block w-[168px] sm:w-[210px] flex-shrink-0 overflow-hidden rounded-xl border border-line bg-white/[0.02] hover:border-accent/40 transition-colors"
                                >
                                    <div className="aspect-[4/3] bg-[#050506] overflow-hidden">
                                        {src ? (
                                            <img
                                                src={src}
                                                alt={image.title || image.filename || 'Agent chart'}
                                                className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.03]"
                                                loading="lazy"
                                            />
                                        ) : (
                                            <div className="h-full w-full flex items-center justify-center text-[10px] text-ink-tertiary font-mono">
                                                Chart unavailable
                                            </div>
                                        )}
                                    </div>
                                    <div className="p-3">
                                        <p className="text-[11px] text-white font-mono uppercase tracking-[0.12em] truncate">
                                            {image.title || image.timeframe || 'Chart'}
                                        </p>
                                        <p className="text-[10px] text-ink-tertiary font-mono mt-1 truncate">
                                            {image.date || image.filename}
                                        </p>
                                    </div>
                                </a>
                            )
                        })}
                    </div>
                </div>
            )}

            {files.length > 0 && (
                <div className="overflow-x-auto no-scrollbar -mx-1 px-1">
                    <div className="flex gap-3 pb-1">
                        {files.map((file, index) => {
                            const href = attachmentFileUrl(file)
                            return (
                                <a
                                    key={`${file.id || file.filename || index}`}
                                    href={href}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="w-[190px] sm:w-[230px] flex-shrink-0 rounded-xl border border-line bg-[#101014] p-4 hover:border-success/40 transition-colors"
                                >
                                    <div className="flex items-center justify-between gap-3">
                                        <div className="h-8 w-8 rounded-lg bg-success/[0.08] border border-success/20 flex items-center justify-center text-[10px] font-mono text-success">
                                            MD
                                        </div>
                                        <span className="text-[9px] font-mono uppercase tracking-[0.16em] text-ink-tertiary">
                                            file
                                        </span>
                                    </div>
                                    <p className="text-[13px] text-white mt-4 truncate">
                                        {file.title || file.filename}
                                    </p>
                                    <p className="text-[10px] text-ink-tertiary font-mono mt-1 truncate">
                                        {file.storage_path || file.path || file.filename || 'artifact.md'}
                                    </p>
                                </a>
                            )
                        })}
                    </div>
                </div>
            )}
        </div>
    )
}

function AgentMetadataPanel({ metadata }: { metadata?: Record<string, any> | null }) {
    const tokenUsage = metadata?.token_usage || metadata?.metrics || {}
    const tokenEntries = Object.entries(tokenUsage).filter(([, value]) => value !== null && value !== undefined)
    const toolCalls = Array.isArray(metadata?.tool_calls) ? metadata?.tool_calls : []
    const reasoningValue = metadata?.reasoning_content || metadata?.reasoning_steps || metadata?.reasoning_messages
    const reasoning = typeof reasoningValue === 'string'
        ? reasoningValue
        : reasoningValue
            ? JSON.stringify(reasoningValue, null, 2)
            : ''

    if (!tokenEntries.length && !toolCalls.length && !reasoning) {
        return (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                {['Thinking tokens', 'Tool calls', 'Reasoning trace'].map((label) => (
                    <div key={label} className="rounded-xl border border-line bg-white/[0.015] p-3">
                        <p className="text-[9px] text-ink-tertiary font-mono uppercase tracking-[0.15em]">{label}</p>
                        <p className="text-[12px] text-ink-secondary mt-1">Not captured in this run</p>
                    </div>
                ))}
            </div>
        )
    }

    return (
        <div className="space-y-3">
            {tokenEntries.length > 0 && (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-line rounded-xl overflow-hidden border border-line">
                    {tokenEntries.map(([key, value]) => (
                        <div key={key} className="bg-[#08080a] p-3">
                            <p className="text-[9px] text-ink-tertiary font-mono uppercase tracking-[0.15em]">
                                {key.replaceAll('_', ' ')}
                            </p>
                            <p className="text-[12px] text-white font-mono nums mt-1 break-words">{String(value)}</p>
                        </div>
                    ))}
                </div>
            )}
            {toolCalls.length > 0 && (
                <div className="rounded-xl border border-line bg-white/[0.015] p-4">
                    <p className="text-[10px] text-accent font-mono uppercase tracking-[0.16em] mb-2">
                        Tool calls
                    </p>
                    <pre className="text-[11px] text-ink-secondary whitespace-pre-wrap break-words max-h-56 overflow-auto">
                        {JSON.stringify(toolCalls, null, 2)}
                    </pre>
                </div>
            )}
            {reasoning && (
                <div className="rounded-xl border border-line bg-white/[0.015] p-4">
                    <p className="text-[10px] text-warning font-mono uppercase tracking-[0.16em] mb-2">
                        Reasoning trace
                    </p>
                    <p className="text-[12px] text-ink-secondary whitespace-pre-wrap leading-relaxed max-h-56 overflow-auto">
                        {reasoning}
                    </p>
                </div>
            )}
        </div>
    )
}

function agentRows(
    runStatus: AgentRunStatus | null,
    liveEvents: Record<number, LiveAgentEvent[]>,
    sessionAgents?: AgentResult[],
) {
    const completedResults: AgentResult[] = sessionAgents?.length
        ? sessionAgents
        : (runStatus?.stages?.stock_agent?.details?.results || [])
    const ranks = Array.from(new Set([
        ...Object.keys(liveEvents).map((rank) => Number(rank)).filter(Boolean),
        ...completedResults.map((item) => Number(item.rank)).filter(Boolean),
    ])).sort((a, b) => a - b)

    return (ranks.length ? ranks : [1]).map((rank) => {
        const events = liveEvents[rank] || []
        const latest = events[events.length - 1]
        const completed = completedResults.find((item) => Number(item.rank) === rank)
        return {
            rank,
            name: agentDisplayName(latest || completed, `Agent ${rank}`),
            status: latest ? eventTitle(latest) : completed ? 'Completed' : 'Waiting',
            complete: latest?.type === 'stock_agent_completed' || Boolean(completed),
            failed: latest?.type === 'stock_agent_failed',
        }
    })
}

function FloatingPanel({
    title,
    open,
    onClose,
    children,
}: {
    title: string
    open: boolean
    onClose: () => void
    children: ReactNode
}) {
    if (!open) return null
    return (
        <div className="fixed inset-0 z-50 pointer-events-none">
            <button
                type="button"
                aria-label={`Close ${title}`}
                className="absolute inset-0 bg-black/40 pointer-events-auto"
                onClick={onClose}
            />
            <motion.div
                initial={{ opacity: 0, y: 18, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ duration: 0.35, ease }}
                className="absolute right-3 left-3 top-24 sm:left-auto sm:right-6 sm:w-[420px] max-h-[72vh] overflow-hidden rounded-2xl border border-line bg-[#08080a]/95 backdrop-blur-xl shadow-2xl pointer-events-auto"
            >
                <div className="flex items-center justify-between gap-4 border-b border-line px-5 py-4">
                    <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-white">
                        {title}
                    </p>
                    <button
                        type="button"
                        onClick={onClose}
                        className="h-8 w-8 rounded-full border border-line text-ink-secondary hover:text-white hover:border-line-strong transition-colors"
                        aria-label={`Close ${title}`}
                    >
                        x
                    </button>
                </div>
                <div className="max-h-[calc(72vh-65px)] overflow-y-auto p-4">
                    {children}
                </div>
            </motion.div>
        </div>
    )
}

function AgentChatBoard({
    runStatus,
    liveEvents,
    sessionAgents,
    activeAgent,
    setActiveAgent,
    connectionState,
}: {
    runStatus: AgentRunStatus | null
    liveEvents: Record<number, LiveAgentEvent[]>
    sessionAgents?: AgentResult[]
    activeAgent: number
    setActiveAgent: (rank: number) => void
    connectionState: string
}) {
    const stockStage = runStatus?.stages?.stock_agent
    const completedResults: AgentResult[] = sessionAgents?.length ? sessionAgents : (stockStage?.details?.results || [])
    const slotRanks = Array.from(
        new Set([
            ...Object.keys(liveEvents).map((rank) => Number(rank)).filter(Boolean),
            ...completedResults.map((item: any) => Number(item.rank)).filter(Boolean),
        ]),
    ).sort((a, b) => a - b)
    const agentSlots = slotRanks.length ? slotRanks : [activeAgent]

    const mergedEvents = (rank: number): LiveAgentEvent[] => {
        const events = liveEvents[rank] || []
        const completed = completedResults.find((item: any) => Number(item.rank) === rank)
        if (completed && !events.some((event) => event.type === 'stock_agent_completed')) {
            return [
                ...events,
                {
                    type: 'stock_agent_completed',
                    rank,
                    symbol: completed.symbol,
                    display_name: completed.display_name,
                    message: 'Completed from latest saved status.',
                    decision: completed.decision,
                    attachments: completed.attachments,
                    agent_metadata: completed.agent_metadata || undefined,
                    report_text: completed.report_text || completed.analysis,
                    error: undefined,
                    sent_at_utc: stockStage?.generated_at_utc || runStatus?.updated_at_utc,
                },
            ]
        }
        return events
    }

    const activeEvents = mergedEvents(activeAgent)
    const activeCompleted = completedResults.find((item: any) => Number(item.rank) === activeAgent)
    const latestActiveEvent = activeEvents[activeEvents.length - 1]
    const activeName = agentDisplayName(
        activeEvents.find((event) => event.display_name || event.symbol) || activeCompleted,
        `Agent ${activeAgent}`,
    )
    const activeAttachments = activeCompleted?.attachments || latestActiveEvent?.attachments
    const activeMetadata = activeCompleted?.agent_metadata || latestActiveEvent?.agent_metadata

    return (
        <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease, delay: 0.18 }}
            className="surface rounded-2xl p-5 border border-line"
        >
            <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 mb-5">
                <div>
                    <p className="text-[10px] font-mono uppercase tracking-[0.22em] text-success">
                        Stock Agents
                    </p>
                    <p className="text-[13px] text-ink-secondary mt-1">
                        Stream: <span className="font-mono uppercase text-[11px]">{connectionState}</span>
                    </p>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
                    {agentSlots.map((rank) => {
                        const events = mergedEvents(rank)
                        const latest = events[events.length - 1]
                        const complete = latest?.type === 'stock_agent_completed'
                        const failed = latest?.type === 'stock_agent_failed'
                        const active = activeAgent === rank
                        return (
                            <button
                                key={rank}
                                type="button"
                                onClick={() => setActiveAgent(rank)}
                                className={`min-w-0 rounded-xl border px-3 py-2 text-left transition-colors ${active
                                    ? 'border-accent/60 bg-accent/10'
                                    : 'border-line bg-[#08080a] hover:border-line-strong'
                                    }`}
                            >
                                <div className="flex items-center gap-2">
                                    <span className={`h-1.5 w-1.5 rounded-full ${failed ? 'bg-danger' : complete ? 'bg-success' : events.length ? 'bg-warning animate-pulse-soft' : 'bg-ink-tertiary'}`} />
                                    <p className="text-[11px] text-white font-mono uppercase tracking-[0.12em] truncate">
                                        Agent {rank}
                                    </p>
                                </div>
                                <p className="text-[10px] text-ink-tertiary font-mono mt-1 truncate">
                                    {latest ? eventTitle(latest) : 'Waiting'}
                                </p>
                            </button>
                        )
                    })}
                </div>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-[280px,1fr] gap-5">
                <div className="space-y-2">
                    {agentSlots.map((rank) => {
                        const events = mergedEvents(rank)
                        const latest = events[events.length - 1]
                        return (
                            <button
                                key={rank}
                                type="button"
                                onClick={() => setActiveAgent(rank)}
                                className={`w-full text-left rounded-xl border p-4 transition-colors ${activeAgent === rank
                                    ? 'border-success/40 bg-success/[0.04]'
                                    : 'border-line bg-white/[0.015] hover:border-line-strong'
                                    }`}
                            >
                                <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-ink-tertiary">
                                    Agent {rank}
                                </p>
                                <p className="text-[13px] text-white mt-1 truncate">
                                    {agentDisplayName(latest || completedResults.find((item: any) => Number(item.rank) === rank))}
                                </p>
                                <p className="text-[11px] text-ink-secondary mt-1 truncate">
                                    {latest?.message || (latest ? eventTitle(latest) : 'No stream events yet')}
                                </p>
                            </button>
                        )
                    })}
                </div>

                <div className="rounded-2xl border border-line bg-[#08080a]/70 overflow-hidden">
                    <div className="border-b border-line px-5 py-4 flex items-center justify-between gap-4">
                        <div className="min-w-0">
                            <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-success">
                                Agent {activeAgent}
                            </p>
                            <h2 className="text-white text-[16px] font-medium mt-1 truncate">
                                {activeName}
                            </h2>
                        </div>
                        <p className="text-[10px] text-ink-tertiary font-mono uppercase tracking-[0.16em]">
                            {activeEvents.length ? eventTitle(activeEvents[activeEvents.length - 1]) : 'Waiting'}
                        </p>
                    </div>
                    <div className="p-4 sm:p-5 space-y-5 min-h-[360px] max-h-[720px] overflow-y-auto">
                        <AttachmentStrip attachments={activeAttachments} />
                        <AgentMetadataPanel metadata={activeMetadata} />
                        {activeEvents.length === 0 ? (
                            <div className="h-full min-h-[300px] flex items-center justify-center border border-dashed border-line rounded-xl">
                                <p className="text-[12px] text-ink-tertiary font-mono">
                                    Waiting for assignment
                                </p>
                            </div>
                        ) : (
                            activeEvents.map((event, index) => (
                                <div key={`${event.type}-${index}-${event.sent_at_utc || ''}`} className="rounded-xl border border-line bg-[#0c0c0f] p-4">
                                    <div className="flex items-center justify-between gap-3 mb-2">
                                        <p className="text-[10px] font-mono uppercase tracking-[0.16em] text-accent">
                                            {eventTitle(event)}
                                        </p>
                                        <p className="text-[10px] text-ink-tertiary font-mono">
                                            {formatTime(event.sent_at_utc)}
                                        </p>
                                    </div>
                                    {event.message && (
                                        <p className="text-[13px] text-ink-secondary leading-relaxed">
                                            {event.message}
                                        </p>
                                    )}
                                    {event.decision && (
                                        <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-line rounded-lg overflow-hidden border border-line mt-3">
                                            {Object.entries(event.decision).slice(0, 8).map(([key, value]) => (
                                                <div key={key} className="bg-[#08080a] p-3">
                                                    <p className="text-[9px] text-ink-tertiary font-mono uppercase tracking-[0.15em]">
                                                        {key.replaceAll('_', ' ')}
                                                    </p>
                                                    <p className="text-[12px] text-white font-mono font-medium break-words nums mt-1">
                                                        {String(value)}
                                                    </p>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                    {event.attachments && <div className="mt-3"><AttachmentStrip attachments={event.attachments} /></div>}
                                    {event.agent_metadata && <div className="mt-3"><AgentMetadataPanel metadata={event.agent_metadata} /></div>}
                                    {(event.report_text || event.error) && (
                                        <p className={`text-[13px] mt-3 whitespace-pre-wrap leading-relaxed ${event.error ? 'text-danger' : 'text-ink-secondary'}`}>
                                            {event.error || event.report_text}
                                        </p>
                                    )}
                                </div>
                            ))
                        )}
                    </div>
                </div>
            </div>
        </motion.div>
    )
}

function TradeHistoryView({
    tradeSessions,
    selectedSession,
    openTradeSession,
    activeAgent,
    setActiveAgent,
}: {
    tradeSessions: TradeSessionSummary[]
    selectedSession: TradeSession | null
    openTradeSession: (sessionId: string) => void
    activeAgent: number
    setActiveAgent: (rank: number) => void
}) {
    const sessionRunStatus = selectedSession?.status_snapshot || null
    const sessionAgents = selectedSession?.agents || []
    const stageMessages = ['stage2'].map((stage) => ({
        stage,
        data: sessionRunStatus?.stages?.[stage],
    }))
    const selectedUpdatedAt = selectedSession?.updated_at_utc || selectedSession?.created_at_utc

    return (
        <div className="grid grid-cols-1 xl:grid-cols-[340px,1fr] gap-6 items-start">
            <aside className="surface rounded-2xl border border-line overflow-hidden xl:sticky xl:top-28">
                <div className="border-b border-line px-5 py-4">
                    <p className="text-[10px] font-mono uppercase tracking-[0.22em] text-success">
                        Past Trades
                    </p>
                    <div className="flex items-end justify-between gap-4 mt-1">
                        <h2 className="text-white text-[18px] font-medium">
                            Trade Sessions
                        </h2>
                        <span className="text-[10px] text-ink-tertiary font-mono uppercase tracking-[0.14em]">
                            {pluralize(tradeSessions.length, 'session')}
                        </span>
                    </div>
                </div>

                {tradeSessions.length === 0 ? (
                    <div className="p-5">
                        <div className="rounded-xl border border-dashed border-line p-8 text-center">
                            <p className="text-[12px] text-ink-tertiary font-mono">
                                No saved trade sessions yet
                            </p>
                        </div>
                    </div>
                ) : (
                    <div className="max-h-[68vh] overflow-y-auto p-3 space-y-2">
                        {tradeSessions.map((session) => {
                            const active = selectedSession?.session_id === session.session_id
                            return (
                                <button
                                    key={session.session_id}
                                    type="button"
                                    onClick={() => openTradeSession(session.session_id)}
                                    className={`w-full rounded-xl border p-4 text-left transition-colors ${active
                                        ? 'border-success/50 bg-success/[0.06]'
                                        : 'border-line bg-white/[0.02] hover:border-line-strong'
                                        }`}
                                >
                                    <div className="flex items-start justify-between gap-3">
                                        <div className="min-w-0">
                                            <p className="text-[10px] font-mono uppercase tracking-[0.16em] text-ink-tertiary">
                                                {formatDateTime(session.updated_at_utc || session.created_at_utc)}
                                            </p>
                                            <p className="text-[14px] text-white mt-1 truncate">
                                                {session.title}
                                            </p>
                                        </div>
                                        <span className={`mt-0.5 h-2 w-2 rounded-full flex-shrink-0 ${session.status === 'completed'
                                            ? 'bg-success'
                                            : session.status === 'failed'
                                                ? 'bg-danger'
                                                : 'bg-warning'
                                            }`}
                                        />
                                    </div>
                                    <div className="mt-3 flex flex-wrap gap-2">
                                        <span className="rounded-full border border-line bg-black/30 px-2.5 py-1 text-[10px] text-ink-secondary font-mono uppercase tracking-[0.12em]">
                                            {session.status}
                                        </span>
                                        <span className="rounded-full border border-line bg-black/30 px-2.5 py-1 text-[10px] text-ink-secondary font-mono uppercase tracking-[0.12em]">
                                            {session.agent_count || 0} agents
                                        </span>
                                        {session.loaded_from_cloud && (
                                            <span className="rounded-full border border-accent/30 bg-accent/[0.08] px-2.5 py-1 text-[10px] text-accent font-mono uppercase tracking-[0.12em]">
                                                cloud
                                            </span>
                                        )}
                                    </div>
                                </button>
                            )
                        })}
                    </div>
                )}
            </aside>

            <section className="min-w-0 space-y-5">
                {!selectedSession ? (
                    <div className="surface rounded-2xl border border-line p-10 text-center min-h-[420px] flex items-center justify-center">
                        <div>
                            <p className="text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary">
                                Session Reader
                            </p>
                            <p className="text-white text-[18px] mt-3">
                                Select a saved trade session to read the agent conversation.
                            </p>
                        </div>
                    </div>
                ) : (
                    <>
                        <motion.div
                            initial={{ opacity: 0, y: 12 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.5, ease }}
                            className="surface rounded-2xl p-5 sm:p-6 border border-line"
                        >
                            <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-5">
                                <div className="min-w-0">
                                    <p className="text-[10px] font-mono uppercase tracking-[0.22em] text-success">
                                        Saved Trade Conversation
                                    </p>
                                    <h2 className="text-white text-[22px] sm:text-[26px] font-medium tracking-[-0.02em] mt-2 break-words">
                                        {selectedSession.title}
                                    </h2>
                                    <p className="text-[12px] text-ink-secondary font-mono mt-3 break-all">
                                        {selectedSession.request_id || selectedSession.session_id}
                                    </p>
                                </div>
                                <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-line rounded-xl overflow-hidden border border-line min-w-0 lg:min-w-[420px]">
                                    {[
                                        ['Status', selectedSession.status],
                                        ['Agents', sessionAgents.length],
                                        ['Executed', selectedSession.summary?.executed_count ?? 0],
                                        ['Updated', formatTime(selectedUpdatedAt)],
                                    ].map(([label, value]) => (
                                        <div key={String(label)} className="bg-[#08080a] p-3">
                                            <p className="text-[9px] text-ink-tertiary font-mono uppercase tracking-[0.15em]">
                                                {label}
                                            </p>
                                            <p className="text-[12px] text-white font-mono nums mt-1 break-words">
                                                {String(value)}
                                            </p>
                                        </div>
                                    ))}
                                </div>
                            </div>
                            <div className="mt-5 flex flex-wrap gap-2">
                                <span className="rounded-full border border-line bg-white/[0.02] px-3 py-1.5 text-[10px] text-ink-secondary font-mono uppercase tracking-[0.14em]">
                                    Created {formatDateTime(selectedSession.created_at_utc)}
                                </span>
                                <span className="rounded-full border border-line bg-white/[0.02] px-3 py-1.5 text-[10px] text-ink-secondary font-mono uppercase tracking-[0.14em]">
                                    {selectedSession.cloud_synced_at_utc ? `Synced ${formatDateTime(selectedSession.cloud_synced_at_utc)}` : 'Local session'}
                                </span>
                                {selectedSession.loaded_from_cloud && (
                                    <span className="rounded-full border border-accent/30 bg-accent/[0.08] px-3 py-1.5 text-[10px] text-accent font-mono uppercase tracking-[0.14em]">
                                        Loaded from Supabase
                                    </span>
                                )}
                            </div>
                        </motion.div>

                        <motion.div
                            initial={{ opacity: 0, y: 12 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.5, ease, delay: 0.05 }}
                            className="flex justify-end"
                        >
                            <div className="max-w-3xl bg-accent/[0.08] border border-accent/30 rounded-2xl rounded-tr-md px-5 py-4">
                                <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-accent mb-1.5">
                                    Operator
                                </p>
                                <p className="text-white text-[14px] leading-relaxed">
                                    Start AI Trading
                                </p>
                                <p className="text-ink-secondary text-[12px] mt-1.5 leading-relaxed">
                                    Saved run from {formatDateTime(selectedSession.created_at_utc)}.
                                </p>
                            </div>
                        </motion.div>

                        <AgentChatBoard
                            runStatus={sessionRunStatus}
                            liveEvents={{}}
                            sessionAgents={sessionAgents}
                            activeAgent={activeAgent}
                            setActiveAgent={setActiveAgent}
                            connectionState={selectedSession.loaded_from_cloud ? 'cloud archive' : 'saved archive'}
                        />

                        {stageMessages.map(({ stage, data }, index) => {
                            const complete = data?.status === 'completed'
                            if (!data) return null
                            return (
                                <motion.div
                                    key={stage}
                                    initial={{ opacity: 0, y: 12 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    transition={{ duration: 0.5, ease, delay: 0.1 + index * 0.05 }}
                                    className="flex justify-start"
                                >
                                    <div className={`max-w-4xl w-full rounded-2xl rounded-tl-md p-5 border ${complete
                                        ? 'border-success/30 bg-success/[0.03]'
                                        : 'border-line bg-[#0a0a0c]/50'
                                        }`}>
                                        <div className="flex items-start justify-between gap-4 mb-3">
                                            <div className="flex items-center gap-3 min-w-0">
                                                <div className={`h-1.5 w-1.5 rounded-full flex-shrink-0 ${complete ? 'bg-success' : 'bg-ink-tertiary'}`} />
                                                <div className="min-w-0">
                                                    <p className="text-white font-medium text-[14px]">
                                                        {stageLabels[stage]}
                                                    </p>
                                                    <p className={`text-[10px] font-mono uppercase tracking-[0.18em] mt-0.5 ${complete ? 'text-success' : 'text-ink-tertiary'}`}>
                                                        {data.status || 'pending'}
                                                    </p>
                                                </div>
                                            </div>
                                            <p className="text-[10px] text-ink-tertiary font-mono flex-shrink-0">
                                                {formatTime(data.generated_at_utc)}
                                            </p>
                                        </div>
                                        <p className="text-[13px] text-ink-secondary mb-4 leading-relaxed">
                                            {statusText(stage, data)}
                                        </p>
                                        {stageBody(stage, data)}
                                    </div>
                                </motion.div>
                            )
                        })}
                    </>
                )}
            </section>
        </div>
    )
}

function AITradingChatContent() {
    const searchParams = useSearchParams()
    const expectedRun = searchParams.get('run')
    const initialView = searchParams.get('view') === 'trades' ? 'trades' : 'live'
    const [runStatus, setRunStatus] = useState<AgentRunStatus | null>(null)
    const [error, setError] = useState<string | null>(null)
    const [liveEvents, setLiveEvents] = useState<Record<number, LiveAgentEvent[]>>({})
    const [activeAgent, setActiveAgent] = useState(1)
    const [connectionState, setConnectionState] = useState('connecting')
    const [viewMode, setViewMode] = useState<'live' | 'trades'>(initialView)
    const [runningPanelOpen, setRunningPanelOpen] = useState(false)
    const [tradeSessions, setTradeSessions] = useState<TradeSessionSummary[]>([])
    const [selectedSession, setSelectedSession] = useState<TradeSession | null>(null)
    const bottomRef = useRef<HTMLDivElement | null>(null)
    const selectedSessionRef = useRef<TradeSession | null>(null)
    const shouldAutoScrollRef = useRef(true)
    const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

    const fetchStatus = async () => {
        if (selectedSessionRef.current) return
        try {
            const response = await fetch('/api/ai-trading/toggle', { method: 'GET' })
            if (!response.ok) throw new Error('Failed to load AI trading status')
            const status = await response.json()
            setRunStatus(status)
            if (!selectedSession) {
                fetchTradeSessions()
            }
            setError(null)
        } catch (statusError) {
            console.error('Error loading AI trading status:', statusError)
            setError('Could not load the latest agent run.')
        }
    }

    useEffect(() => {
        selectedSessionRef.current = selectedSession
    }, [selectedSession])

    const fetchTradeSessions = async () => {
        try {
            const response = await fetch('/api/ai-trading/sessions', { method: 'GET', cache: 'no-store' })
            if (!response.ok) return
            const payload = await response.json()
            setTradeSessions(Array.isArray(payload.sessions) ? payload.sessions : [])
        } catch (sessionError) {
            console.error('Error loading trade sessions:', sessionError)
        }
    }

    const openTradeSession = async (sessionId: string) => {
        try {
            const response = await fetch(`/api/ai-trading/sessions/${encodeURIComponent(sessionId)}`, {
                method: 'GET',
                cache: 'no-store',
            })
            if (!response.ok) throw new Error('Failed to load trade session')
            const session: TradeSession = await response.json()
            setSelectedSession(session)
            setRunStatus(session.status_snapshot || null)
            setLiveEvents({})
            const firstRank = Number(session.agents?.[0]?.rank || 1)
            setActiveAgent(firstRank)
            setViewMode('trades')
        } catch (sessionError) {
            console.error('Error opening trade session:', sessionError)
            setError('Could not open that trade session.')
        }
    }

    const resumeLiveRun = () => {
        setSelectedSession(null)
        setLiveEvents({})
        setViewMode('live')
        fetchStatus()
    }

    useEffect(() => {
        fetchStatus()
        fetchTradeSessions()
        const timer = setInterval(fetchStatus, 2500)
        return () => clearInterval(timer)
    }, [])

    useEffect(() => {
        if (viewMode === 'trades') {
            fetchTradeSessions()
        }
    }, [viewMode])

    useEffect(() => {
        if (viewMode === 'trades' && !selectedSession && tradeSessions.length > 0) {
            openTradeSession(tradeSessions[0].session_id)
        }
    }, [viewMode, tradeSessions, selectedSession])

    useEffect(() => {
        let socket: WebSocket | null = null
        let closedByEffect = false

        const connect = () => {
            const url = websocketUrl()
            if (!url) {
                setConnectionState('unavailable')
                return
            }
            try {
                setConnectionState('connecting')
                socket = new WebSocket(url)
            } catch (socketError) {
                console.error('AI trading stream setup failed:', socketError)
                setConnectionState('fallback')
                return
            }

            socket.onopen = () => {
                setConnectionState('live')
            }

            socket.onmessage = (event) => {
                try {
                    const payload = JSON.parse(event.data)
                    if (selectedSessionRef.current) return
                    if (payload.type === 'heartbeat') return
                    if (payload.type === 'status_snapshot' && payload.status) {
                        setRunStatus(payload.status)
                        return
                    }
                    if (payload.type === 'status_update' && payload.status) {
                        setRunStatus(payload.status)
                        return
                    }
                    if (payload.type === 'stock_agent_selection') {
                        const nextEvents: Record<number, LiveAgentEvent[]> = {}
                        for (const selected of payload.selected || []) {
                            const rank = Number(selected.rank || 0)
                            if (!rank) continue
                            nextEvents[rank] = [
                                {
                                    type: 'stock_agent_selection',
                                    rank,
                                    security_id: selected.security_id,
                                    symbol: selected.symbol,
                                    display_name: selected.display_name,
                                    message: 'Selected from Stage 2 scan.',
                                    sent_at_utc: payload.sent_at_utc,
                                },
                            ]
                        }
                        setLiveEvents(nextEvents)
                        setActiveAgent(1)
                        return
                    }
                    if (payload.type === 'stock_agent_no_trade') {
                        setLiveEvents({
                            1: [{
                                type: 'stock_agent_no_trade',
                                rank: 1,
                                message: payload.reason || 'No stock qualified.',
                                sent_at_utc: payload.sent_at_utc,
                            }],
                        })
                        setActiveAgent(1)
                        return
                    }
                    if (typeof payload.rank === 'number') {
                        const rank = Number(payload.rank)
                        setLiveEvents((current) => ({
                            ...current,
                            [rank]: [
                                ...(current[rank] || []),
                                {
                                    type: payload.type,
                                    rank,
                                    security_id: payload.security_id,
                                    symbol: payload.symbol,
                                    display_name: payload.display_name,
                                    message: payload.message,
                                    decision: payload.decision,
                                    attachments: payload.attachments,
                                    agent_metadata: payload.agent_metadata,
                                    chart_count: payload.chart_count,
                                    report_text: payload.report_text,
                                    error: payload.error,
                                    sent_at_utc: payload.sent_at_utc,
                                },
                            ],
                        }))
                    }
                } catch (streamError) {
                    console.error('AI trading stream payload error:', streamError)
                }
            }

            socket.onerror = () => {
                setConnectionState('fallback')
            }

            socket.onclose = () => {
                if (closedByEffect) return
                setConnectionState('reconnecting')
                reconnectTimerRef.current = setTimeout(connect, 2500)
            }
        }

        connect()
        return () => {
            closedByEffect = true
            if (reconnectTimerRef.current) {
                clearTimeout(reconnectTimerRef.current)
            }
            socket?.close()
        }
    }, [])

    useEffect(() => {
        const handleScroll = () => {
            const distanceFromBottom =
                document.documentElement.scrollHeight - window.scrollY - window.innerHeight
            shouldAutoScrollRef.current = distanceFromBottom < 180
        }

        handleScroll()
        window.addEventListener('scroll', handleScroll, { passive: true })
        return () => window.removeEventListener('scroll', handleScroll)
    }, [])

    useEffect(() => {
        if (shouldAutoScrollRef.current) {
            bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
        }
    }, [runStatus])

    const messages = useMemo(() => {
        const stages = runStatus?.stages || {}
        return ['stage2'].map((stage) => ({
            stage,
            data: stages[stage],
        }))
    }, [runStatus])

    const isRunning = runStatus?.status === 'running'
    const statusAccent = isRunning ? 'text-warning' : runStatus?.status === 'completed' ? 'text-success' : 'text-accent'
    const sessionAgents = selectedSession?.agents || []
    const rows = agentRows(runStatus, liveEvents, sessionAgents)

    return (
        <div className="relative min-h-screen bg-[#050505] text-white overflow-x-hidden">
            {/* Ambient backdrop */}
            <div className="pointer-events-none fixed inset-0 bg-grid-fine opacity-50" />
            <div className="pointer-events-none fixed inset-0 bg-spotlight" />

            {/* Header */}
            <header className="sticky top-0 z-40">
                <div className="mx-auto max-w-6xl px-4 sm:px-6 pt-5">
                    <div className="glass rounded-2xl sm:rounded-full px-4 sm:px-6 py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                        <div className="flex items-center gap-3 sm:gap-4 min-w-0">
                            <Link href="/" className="flex items-center gap-2.5 flex-shrink-0" aria-label="Home">
                                <div className="relative h-7 w-7">
                                    <div className="absolute inset-0 rounded-full bg-gradient-to-br from-accent to-success opacity-80 blur-md" />
                                    <div className="absolute inset-[3px] rounded-full bg-[#0a0a0c] flex items-center justify-center">
                                        <div className="h-1.5 w-1.5 rounded-full bg-white" />
                                    </div>
                                </div>
                            </Link>
                            <div className="border-l border-white/10 pl-3 sm:pl-4 min-w-0">
                                <p className="text-[10px] font-mono uppercase tracking-[0.22em] text-success">
                                    {viewMode === 'trades' ? 'Trade History' : 'Live Agent Run'}
                                </p>
                                <h1 className="font-display text-[18px] sm:text-[20px] text-white tracking-[-0.02em] leading-[1.1] mt-0.5">
                                    AI Trading <span className="font-serif-italic text-ink-secondary">{viewMode === 'trades' ? 'Sessions' : 'Terminal'}</span>
                                </h1>
                            </div>
                        </div>
                        <div className="flex items-center gap-2 w-full sm:w-auto overflow-x-auto no-scrollbar">
                            {viewMode === 'trades' && (
                                <button
                                    type="button"
                                    onClick={resumeLiveRun}
                                    className="flex-shrink-0 rounded-full border border-line bg-white/[0.03] px-4 py-2 text-[11px] font-mono uppercase tracking-[0.14em] text-white hover:border-line-strong transition-colors"
                                >
                                    Live
                                </button>
                            )}
                            <button
                                type="button"
                                onClick={() => setRunningPanelOpen(true)}
                                className="flex-shrink-0 rounded-full border border-accent/30 bg-accent/[0.08] px-4 py-2 text-[11px] font-mono uppercase tracking-[0.14em] text-white hover:border-accent/60 transition-colors"
                            >
                                running agents
                            </button>
                            <button
                                type="button"
                                onClick={() => {
                                    fetchTradeSessions()
                                    setViewMode('trades')
                                }}
                                className={`flex-shrink-0 rounded-full border px-4 py-2 text-[11px] font-mono uppercase tracking-[0.14em] text-white transition-colors ${viewMode === 'trades'
                                    ? 'border-success/50 bg-success/[0.08]'
                                    : 'border-line bg-white/[0.03] hover:border-line-strong'
                                    }`}
                            >
                                Trades
                            </button>
                            <Link href="/dashboard" className="flex-shrink-0 rounded-full border border-line bg-white/[0.03] px-4 py-2 text-[11px] font-mono uppercase tracking-[0.14em] text-white hover:border-line-strong transition-colors">
                                Dashboard
                            </Link>
                        </div>
                    </div>
                </div>
            </header>

            <FloatingPanel
                title="running agents"
                open={runningPanelOpen}
                onClose={() => setRunningPanelOpen(false)}
            >
                <div className="space-y-2">
                    {rows.map((row) => (
                        <button
                            key={row.rank}
                            type="button"
                            onClick={() => {
                                setActiveAgent(row.rank)
                                setRunningPanelOpen(false)
                                bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
                            }}
                            className={`w-full rounded-xl border p-4 text-left transition-colors ${activeAgent === row.rank
                                ? 'border-accent/50 bg-accent/[0.08]'
                                : 'border-line bg-white/[0.02] hover:border-line-strong'
                                }`}
                        >
                            <div className="flex items-start justify-between gap-3">
                                <div className="min-w-0">
                                    <p className="text-[10px] font-mono uppercase tracking-[0.16em] text-ink-tertiary">
                                        Agent {row.rank}
                                    </p>
                                    <p className="text-[14px] text-white mt-1 truncate">
                                        {row.name}
                                    </p>
                                </div>
                                <span className={`mt-1 h-2 w-2 rounded-full flex-shrink-0 ${row.failed ? 'bg-danger' : row.complete ? 'bg-success' : 'bg-warning animate-pulse-soft'}`} />
                            </div>
                            <p className="text-[11px] text-ink-secondary mt-2 truncate">
                                {row.status}
                            </p>
                        </button>
                    ))}
                </div>
            </FloatingPanel>

            <main className="relative mx-auto max-w-6xl px-6 lg:px-8 pt-10 pb-24">
                {/* Run metadata */}
                <motion.div
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.6, ease }}
                    className="mb-8 surface rounded-2xl p-6"
                >
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        <div className="md:col-span-2">
                            <span className="text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary">
                                Run ID
                            </span>
                            <p className="text-[12px] text-white font-mono break-all mt-2">
                                {runStatus?.request?.request_id || expectedRun || 'Waiting for request'}
                            </p>
                        </div>
                        <div>
                            <span className="text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary">
                                Status
                            </span>
                            <div className="flex items-center gap-2 mt-2">
                                <span className={`relative flex h-1.5 w-1.5`}>
                                    <span className={`absolute inline-flex h-full w-full rounded-full ${isRunning ? 'bg-warning' : runStatus?.status === 'completed' ? 'bg-success' : 'bg-accent'} opacity-60 animate-pulse-ring`} />
                                    <span className={`relative inline-flex h-1.5 w-1.5 rounded-full ${isRunning ? 'bg-warning' : runStatus?.status === 'completed' ? 'bg-success' : 'bg-accent'}`} />
                                </span>
                                <p className={`text-[14px] font-mono font-medium uppercase tracking-[0.15em] ${statusAccent}`}>
                                    {runStatus?.status || 'loading'}
                                </p>
                            </div>
                        </div>
                    </div>
                    {runStatus?.message && (
                        <div className="mt-5 pt-5 border-t border-line">
                            <p className="text-[12px] text-warning font-mono">
                                {runStatus.message}
                            </p>
                        </div>
                    )}
                </motion.div>

                {error && (
                    <motion.div
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="mb-8 border border-danger/40 bg-danger/[0.06] rounded-xl px-4 py-3"
                    >
                        <p className="text-danger font-mono text-[12px] font-medium">
                            {error}
                        </p>
                    </motion.div>
                )}

                {viewMode === 'trades' ? (
                    <TradeHistoryView
                        tradeSessions={tradeSessions}
                        selectedSession={selectedSession}
                        openTradeSession={openTradeSession}
                        activeAgent={activeAgent}
                        setActiveAgent={setActiveAgent}
                    />
                ) : (
                    <div className="space-y-5 pb-8">
                        {/* Conversation stream */}
                    {/* User input bubble */}
                    <motion.div
                        initial={{ opacity: 0, y: 12 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.6, ease, delay: 0.1 }}
                        className="flex justify-end"
                    >
                        <div className="max-w-3xl bg-accent/[0.08] border border-accent/30 rounded-2xl rounded-tr-md px-5 py-4">
                            <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-accent mb-1.5">
                                Operator
                            </p>
                            <p className="text-white text-[14px] leading-relaxed">
                                Start AI Trading
                            </p>
                            <p className="text-ink-secondary text-[12px] mt-1.5 leading-relaxed">
                                Run the stock agents once, only after Stage 2 is ready.
                            </p>
                        </div>
                    </motion.div>

                    <AgentChatBoard
                        runStatus={runStatus}
                        liveEvents={liveEvents}
                        sessionAgents={sessionAgents}
                        activeAgent={activeAgent}
                        setActiveAgent={setActiveAgent}
                        connectionState={connectionState}
                    />

                    {messages.map(({ stage, data }, index) => {
                        const active = data?.status === 'running'
                        const complete = data?.status === 'completed'
                        const pending = !data || data.status === 'pending'
                        return (
                            <motion.div
                                key={stage}
                                initial={{ opacity: 0, y: 12 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ duration: 0.6, ease, delay: 0.2 + index * 0.08 }}
                                className="flex justify-start"
                            >
                                <div className={`max-w-4xl w-full rounded-2xl rounded-tl-md p-5 border ${complete
                                    ? 'border-success/30 bg-success/[0.03]'
                                    : active
                                        ? 'border-warning/30 bg-warning/[0.03]'
                                        : 'border-line bg-[#0a0a0c]/50'
                                    }`}>
                                    <div className="flex items-start justify-between gap-4 mb-3">
                                        <div className="flex items-center gap-3 min-w-0">
                                            <div className={`h-1.5 w-1.5 rounded-full flex-shrink-0 ${complete ? 'bg-success' : active ? 'bg-warning animate-pulse-soft' : 'bg-ink-tertiary'}`} />
                                            <div className="min-w-0">
                                                <p className="text-white font-medium text-[14px]">
                                                    {stageLabels[stage]}
                                                </p>
                                                <p className={`text-[10px] font-mono uppercase tracking-[0.18em] mt-0.5 ${complete ? 'text-success' : active ? 'text-warning' : 'text-ink-tertiary'}`}>
                                                    {data?.status || 'pending'}
                                                </p>
                                            </div>
                                        </div>
                                        <p className="text-[10px] text-ink-tertiary font-mono flex-shrink-0">
                                            {formatTime(data?.generated_at_utc)}
                                        </p>
                                    </div>
                                    <p className="text-[13px] text-ink-secondary mb-4 leading-relaxed">
                                        {statusText(stage, data)}
                                    </p>
                                    {stageBody(stage, data)}
                                </div>
                            </motion.div>
                        )
                    })}

                    {runStatus?.error && (
                        <motion.div
                            initial={{ opacity: 0, y: 12 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="flex justify-start"
                        >
                            <div className="max-w-4xl w-full border border-danger/40 bg-danger/[0.04] rounded-2xl rounded-tl-md p-5">
                                <p className="text-danger font-mono text-[10px] uppercase tracking-[0.18em] mb-1.5">
                                    Run failed
                                </p>
                                <p className="text-ink-secondary text-[13px] mt-1.5 leading-relaxed">
                                    {runStatus.error}
                                </p>
                            </div>
                        </motion.div>
                    )}

                    {runStatus?.status === 'completed' && (
                        <motion.div
                            initial={{ opacity: 0, y: 12 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="flex justify-end gap-3 pt-2"
                        >
                            <Link
                                href="/dashboard"
                                className="btn-secondary !px-5 !py-2.5 !text-[12px]"
                            >
                                Back to Dashboard
                            </Link>
                            <button
                                onClick={() => window.location.href = '/dashboard'}
                                className="btn-primary !px-5 !py-2.5 !text-[12px]"
                            >
                                <span>Trade Again</span>
                                <span className="text-[10px]">→</span>
                            </button>
                        </motion.div>
                    )}
                    <div ref={bottomRef} />
                    </div>
                )}
            </main>
        </div>
    )
}

export default function AITradingChatPage() {
    return (
        <Suspense fallback={
            <div className="min-h-screen bg-[#050505] flex items-center justify-center">
                <div className="flex flex-col items-center gap-5">
                    <div className="relative h-10 w-10">
                        <span className="absolute inline-flex h-full w-full rounded-full bg-accent opacity-40 animate-pulse-ring" />
                        <span className="relative inline-flex h-10 w-10 rounded-full border border-accent/40" />
                    </div>
                    <p className="text-[11px] font-mono uppercase tracking-[0.22em] text-ink-tertiary">
                        Loading terminal
                    </p>
                </div>
            </div>
        }>
            <AITradingChatContent />
        </Suspense>
    )
}
