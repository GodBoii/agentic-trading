'use client'

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { motion } from 'framer-motion'
import AgentMarkdown from '@/components/agent-markdown'
import TradingStatus from '@/components/trading-status'
import { TradeHistoryArchive, type TradeSessionSummary } from '@/components/trade-history-archive'

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
    sequence?: number
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
    created_at?: number
    input?: Record<string, any>
    tool_call_id?: string
    tool_name?: string
    tool_args?: Record<string, any>
    duration_seconds?: number
    result_length?: number
    result_preview?: string
    result?: string
    result_status?: string
    result_partial?: boolean
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
                        <div className="mt-2">
                            <AgentMarkdown>{result.report_text || result.analysis}</AgentMarkdown>
                        </div>
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
            <AgentMarkdown>{data.details?.report_text}</AgentMarkdown>
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
    if (event.type === 'stock_agent_input') return 'Input'
    if (event.type === 'stock_agent_thinking') return 'Thinking'
    if (event.type === 'stock_agent_tool_call_started') return `Tool · ${event.tool_name || 'Started'}`
    if (event.type === 'stock_agent_tool_call_completed') return `Tool · ${event.tool_name || 'Completed'}`
    if (event.type === 'stock_agent_tool_call_error') return `Tool · ${event.tool_name || 'Failed'}`
    if (event.type === 'stock_agent_response_delta') return 'Response'
    if (event.type === 'stock_agent_run_error') return 'Run error'
    return event.type.replaceAll('_', ' ')
}

function coalesceAgentEvents(events: LiveAgentEvent[]) {
    const merged: LiveAgentEvent[] = []
    for (const event of events) {
        const previous = merged[merged.length - 1]
        const mergeable = event.type === 'stock_agent_thinking' || event.type === 'stock_agent_response_delta'
        if (previous && mergeable && previous.type === event.type) {
            previous.message = `${previous.message || ''}${event.message || ''}`
            previous.sequence = event.sequence || previous.sequence
            previous.sent_at_utc = event.sent_at_utc || previous.sent_at_utc
            continue
        }
        merged.push({ ...event })
    }
    return merged
}

function ToolTimelineCard({ event }: { event: LiveAgentEvent }) {
    const completed = event.type === 'stock_agent_tool_call_completed'
    const failed = event.type === 'stock_agent_tool_call_error'
    const status = failed ? 'Failed' : completed ? (event.result_partial ? 'Partial' : 'Succeeded') : 'Running'
    const tone = failed ? 'text-danger' : completed ? (event.result_partial ? 'text-warning' : 'text-success') : 'text-accent'
    return (
        <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
                <span className={`font-mono text-[11px] font-medium ${tone}`}>{status}</span>
                {event.duration_seconds !== undefined && (
                    <span className="font-mono text-[10px] text-ink-tertiary">{event.duration_seconds.toFixed(2)}s</span>
                )}
                {event.result_length !== undefined && (
                    <span className="font-mono text-[10px] text-ink-tertiary">{event.result_length.toLocaleString()} characters</span>
                )}
            </div>
            {event.tool_args && Object.keys(event.tool_args).length > 0 && (
                <details className="rounded-xl border border-line bg-black/20 p-3">
                    <summary className="cursor-pointer font-mono text-[9px] uppercase tracking-[0.15em] text-ink-tertiary">Arguments</summary>
                    <pre className="mt-3 max-h-48 overflow-auto whitespace-pre-wrap break-words text-[11px] text-ink-secondary">
                        {JSON.stringify(event.tool_args, null, 2)}
                    </pre>
                </details>
            )}
            {(event.result_preview || event.result) && (
                <details className="rounded-xl border border-line bg-black/20 p-3" open={failed}>
                    <summary className="cursor-pointer font-mono text-[9px] uppercase tracking-[0.15em] text-ink-tertiary">
                        {event.result ? 'Tool result' : 'Result preview'}
                    </summary>
                    <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap break-words text-[11px] text-ink-secondary">
                        {event.result || event.result_preview}
                    </pre>
                </details>
            )}
        </div>
    )
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
                <div className="attachment-rail -mx-1 px-1 pb-2">
                    <div className="flex min-w-max gap-3 pb-2">
                        {images.map((image, index) => {
                            const src = attachmentImageUrl(image)
                            return (
                                <a
                                    key={`${image.id || image.filename || index}`}
                                    href={src}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="group block w-[220px] sm:w-[280px] flex-shrink-0 overflow-hidden rounded-xl border border-line bg-white/[0.02] hover:border-accent/40 transition-colors"
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
                <div className="attachment-rail -mx-1 px-1 pb-2">
                    <div className="flex min-w-max gap-3 pb-2">
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
    const toolSummary = metadata?.tool_summary || {}
    const summaryEntries = Object.entries(toolSummary).filter(
        ([key, value]) => key !== 'largest_result' && value !== null && value !== undefined,
    )

    if (!tokenEntries.length && !toolCalls.length && !reasoning && !summaryEntries.length) {
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
            {summaryEntries.length > 0 && (
                <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-4">
                    {summaryEntries.map(([key, value]) => (
                        <div key={key} className="bg-[#08080a] p-3">
                            <p className="font-mono text-[9px] uppercase tracking-[0.15em] text-ink-tertiary">
                                {key.replaceAll('_', ' ')}
                            </p>
                            <p className="nums mt-1 break-words font-mono text-[12px] text-white">{String(value)}</p>
                        </div>
                    ))}
                </div>
            )}
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
            {(toolCalls.length > 0 || reasoning) && (
                <details className="rounded-xl border border-line bg-white/[0.015] p-4">
                    <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-[0.16em] text-ink-tertiary">
                        Raw run metadata
                    </summary>
                    {toolCalls.length > 0 && (
                        <pre className="mt-4 max-h-56 overflow-auto whitespace-pre-wrap break-words text-[11px] text-ink-secondary">
                            {JSON.stringify(toolCalls, null, 2)}
                        </pre>
                    )}
                    {reasoning && (
                        <div className="mt-4 max-h-80 overflow-auto border-t border-line pt-4">
                            <AgentMarkdown>{reasoning}</AgentMarkdown>
                        </div>
                    )}
                </details>
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
        let events = liveEvents[rank] || []
        const completed = completedResults.find((item: any) => Number(item.rank) === rank)
        if (!events.length && Array.isArray(completed?.agent_metadata?.timeline)) {
            events = completed.agent_metadata.timeline.map((event: LiveAgentEvent) => ({
                ...event,
                rank,
                symbol: event.symbol || completed.symbol,
                display_name: event.display_name || completed.display_name,
                sent_at_utc: event.sent_at_utc || (event.created_at ? new Date(event.created_at * 1000).toISOString() : undefined),
            }))
        }
        if (completed && !events.some((event) => event.type === 'stock_agent_completed')) {
            return coalesceAgentEvents([
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
            ])
        }
        return coalesceAgentEvents(events)
    }

    const [focusedAgent, setFocusedAgent] = useState<number | null>(null)
    const runIdentity = runStatus?.request?.request_id || sessionAgents?.[0]?.symbol || 'current'

    useEffect(() => {
        setFocusedAgent(null)
    }, [runIdentity])

    const focusAgent = (rank: number) => {
        setActiveAgent(rank)
        setFocusedAgent(rank)
    }

    if (focusedAgent === null) {
        return (
            <motion.section
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, ease }}
                className="surface min-h-[calc(100vh-240px)] rounded-3xl border border-line p-5 sm:p-8"
            >
                <div className="flex flex-col justify-between gap-5 border-b border-line pb-6 sm:flex-row sm:items-end">
                    <div>
                        <p className="text-[10px] font-mono uppercase tracking-[0.22em] text-success">
                            Agent run
                        </p>
                        <h2 className="mt-2 text-[26px] font-semibold tracking-[-0.035em] text-white sm:text-[34px]">
                            Running agents
                        </h2>
                        <p className="mt-2 max-w-xl text-[13px] leading-relaxed text-ink-secondary">
                            Select an agent to open its live workspace, charts, files, decisions, and response.
                        </p>
                    </div>
                    <div className="flex items-center gap-2 rounded-full border border-line bg-black/30 px-3 py-2">
                        <span className={`h-2 w-2 rounded-full ${connectionState.includes('live') ? 'bg-success' : 'bg-warning animate-pulse-soft'}`} />
                        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-ink-secondary">
                            {connectionState}
                        </span>
                    </div>
                </div>

                <div className="attachment-rail mt-7 pb-3">
                    <div className="flex min-w-max gap-3 pb-3">
                        {agentSlots.map((rank) => {
                            const events = mergedEvents(rank)
                            const latest = events[events.length - 1]
                            const completed = completedResults.find((item: any) => Number(item.rank) === rank)
                            const complete = latest?.type === 'stock_agent_completed' || Boolean(completed)
                            const failed = latest?.type === 'stock_agent_failed'
                            const name = agentDisplayName(latest || completed, `Agent ${rank}`)
                            return (
                                <button
                                    key={rank}
                                    type="button"
                                    onClick={() => focusAgent(rank)}
                                    className="group w-[220px] flex-shrink-0 rounded-2xl border border-line bg-[#0a0a0d] p-4 text-left transition-all hover:-translate-y-0.5 hover:border-accent/50 hover:bg-accent/[0.04]"
                                >
                                    <div className="flex items-center justify-between gap-3">
                                        <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-ink-tertiary">
                                            Agent {rank}
                                        </span>
                                        <span className={`h-2 w-2 rounded-full ${failed ? 'bg-danger' : complete ? 'bg-success' : events.length ? 'bg-warning animate-pulse-soft' : 'bg-ink-tertiary'}`} />
                                    </div>
                                    <p className="mt-5 truncate text-[15px] font-medium text-white">{name}</p>
                                    <p className="mt-1 truncate text-[11px] text-ink-secondary">
                                        {latest ? eventTitle(latest) : 'Waiting for assignment'}
                                    </p>
                                    <div className="mt-5 flex items-center justify-between border-t border-line pt-3">
                                        <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-ink-tertiary">
                                            {complete ? 'Complete' : failed ? 'Failed' : 'Open workspace'}
                                        </span>
                                        <span className="text-[14px] text-accent transition-transform group-hover:translate-x-1">→</span>
                                    </div>
                                </button>
                            )
                        })}
                    </div>
                </div>

                {agentSlots.length === 1 && mergedEvents(agentSlots[0]).length === 0 && (
                    <div className="mt-4 grid min-h-[240px] place-items-center rounded-2xl border border-dashed border-line">
                        <div className="text-center">
                            <span className="mx-auto block h-2 w-2 animate-pulse rounded-full bg-warning" />
                            <p className="mt-4 font-mono text-[10px] uppercase tracking-[0.18em] text-ink-tertiary">
                                Waiting for agent selection
                            </p>
                        </div>
                    </div>
                )}
            </motion.section>
        )
    }

    const activeEvents = mergedEvents(focusedAgent)
    const activeCompleted = completedResults.find((item: any) => Number(item.rank) === focusedAgent)
    const latestActiveEvent = activeEvents[activeEvents.length - 1]
    const activeName = agentDisplayName(
        activeEvents.find((event) => event.display_name || event.symbol) || activeCompleted,
        `Agent ${focusedAgent}`,
    )
    const activeAttachments = activeCompleted?.attachments || latestActiveEvent?.attachments
    const activeMetadata = activeCompleted?.agent_metadata || latestActiveEvent?.agent_metadata

    return (
        <motion.section
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, ease }}
            className="min-h-[calc(100vh-150px)]"
        >
            <div className="sticky top-[88px] z-30 mb-5 flex items-center justify-between gap-4 rounded-2xl border border-line bg-[#08080a]/95 px-4 py-3 backdrop-blur-xl sm:px-5">
                <button
                    type="button"
                    onClick={() => setFocusedAgent(null)}
                    className="flex items-center gap-2 rounded-full border border-line px-3 py-2 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-secondary transition-colors hover:border-line-strong hover:text-white"
                >
                    <span aria-hidden>←</span>
                    All agents
                </button>
                <div className="min-w-0 text-right">
                    <p className="font-mono text-[9px] uppercase tracking-[0.18em] text-success">Agent {focusedAgent}</p>
                    <p className="truncate text-[14px] font-medium text-white">{activeName}</p>
                </div>
            </div>

            <div className="surface overflow-hidden rounded-3xl border border-line">
                <div className="flex flex-col justify-between gap-5 border-b border-line px-5 py-6 sm:flex-row sm:items-end sm:px-8">
                    <div>
                        <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-accent">
                            Agent workspace
                        </p>
                        <h2 className="mt-2 text-[28px] font-semibold tracking-[-0.035em] text-white sm:text-[38px]">
                            {activeName}
                        </h2>
                    </div>
                    <span className="self-start rounded-full border border-line bg-black/30 px-3 py-1.5 font-mono text-[9px] uppercase tracking-[0.16em] text-ink-secondary sm:self-auto">
                        {latestActiveEvent ? eventTitle(latestActiveEvent) : 'Waiting'}
                    </span>
                </div>

                <div className="space-y-6 p-4 sm:p-8">
                    <AttachmentStrip attachments={activeAttachments} />
                    <AgentMetadataPanel metadata={activeMetadata} />

                    {activeEvents.length === 0 ? (
                        <div className="grid min-h-[340px] place-items-center rounded-2xl border border-dashed border-line">
                            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-tertiary">
                                Waiting for agent output
                            </p>
                        </div>
                    ) : (
                        <div className="space-y-4">
                            {activeEvents.map((event, index) => (
                                <article key={`${event.type}-${index}-${event.sent_at_utc || ''}`} className="rounded-2xl border border-line bg-[#0b0b0e] p-4 sm:p-6">
                                    <div className="mb-4 flex items-center justify-between gap-3">
                                        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent">
                                            {eventTitle(event)}
                                        </p>
                                        <p className="font-mono text-[9px] text-ink-tertiary">
                                            {formatTime(event.sent_at_utc)}
                                        </p>
                                    </div>

                                    {event.message && <AgentMarkdown>{event.message}</AgentMarkdown>}

                                    {event.type.startsWith('stock_agent_tool_call_') && (
                                        <div className={event.message ? 'mt-4' : ''}>
                                            <ToolTimelineCard event={event} />
                                        </div>
                                    )}

                                    {event.input && (
                                        <details className="mt-4 rounded-xl border border-line bg-black/20 p-3">
                                            <summary className="cursor-pointer font-mono text-[9px] uppercase tracking-[0.15em] text-ink-tertiary">
                                                Structured input
                                            </summary>
                                            <pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap break-words text-[11px] text-ink-secondary">
                                                {JSON.stringify(event.input, null, 2)}
                                            </pre>
                                        </details>
                                    )}

                                    {event.decision && (
                                        <div className="mt-4 grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line md:grid-cols-4">
                                            {Object.entries(event.decision).slice(0, 8).map(([key, value]) => (
                                                <div key={key} className="bg-[#08080a] p-3">
                                                    <p className="font-mono text-[9px] uppercase tracking-[0.15em] text-ink-tertiary">
                                                        {key.replaceAll('_', ' ')}
                                                    </p>
                                                    <p className="nums mt-1 break-words font-mono text-[12px] font-medium text-white">
                                                        {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                                                    </p>
                                                </div>
                                            ))}
                                        </div>
                                    )}

                                    {event.report_text && event.report_text !== event.message && (
                                        <div className="mt-5 border-t border-line pt-5">
                                            <AgentMarkdown>{event.report_text}</AgentMarkdown>
                                        </div>
                                    )}
                                    {event.error && (
                                        <div className="mt-5 border-t border-danger/20 pt-5">
                                            <AgentMarkdown tone="danger">{event.error}</AgentMarkdown>
                                        </div>
                                    )}
                                </article>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </motion.section>
    )
}

function TradeHistoryView({
    tradeSessions,
    selectedSession,
    openTradeSession,
    prefetchTradeSession,
    closeTradeSession,
    activeAgent,
    setActiveAgent,
    sessionsLoading,
    openingSessionId,
    sessionsError,
    retryTradeSessions,
}: {
    tradeSessions: TradeSessionSummary[]
    selectedSession: TradeSession | null
    openTradeSession: (sessionId: string) => void
    prefetchTradeSession: (sessionId: string) => void
    closeTradeSession: () => void
    activeAgent: number
    setActiveAgent: (rank: number) => void
    sessionsLoading: boolean
    openingSessionId: string | null
    sessionsError: string | null
    retryTradeSessions: () => void
}) {
    if (selectedSession) {
        const sessionAgents = selectedSession.agents || []
        const selectedUpdatedAt = selectedSession.updated_at_utc || selectedSession.created_at_utc
        return (
            <motion.section
                initial={{ opacity: 0, x: 8, filter: 'blur(3px)' }}
                animate={{ opacity: 1, x: 0, filter: 'blur(0px)' }}
                transition={{ duration: 0.25, ease }}
                className="space-y-5"
            >
                <button
                    type="button"
                    onClick={closeTradeSession}
                    className="archive-back-button flex items-center gap-2 rounded-full border border-line px-3 py-2 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-secondary hover:border-line-strong hover:text-white"
                >
                    <span aria-hidden>←</span>
                    Trade history
                </button>

                <div className="surface rounded-3xl border border-line p-5 sm:p-8">
                    <div className="flex flex-col justify-between gap-6 lg:flex-row lg:items-end">
                        <div className="min-w-0">
                            <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-success">
                                Archived agent run
                            </p>
                            <h2 className="mt-2 max-w-3xl break-words text-[26px] font-semibold tracking-[-0.035em] text-white sm:text-[36px]">
                                {selectedSession.title}
                            </h2>
                            <p className="mt-3 break-all font-mono text-[10px] text-ink-tertiary">
                                {selectedSession.request_id || selectedSession.session_id}
                            </p>
                        </div>
                        <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-4 lg:min-w-[430px]">
                            {[
                                ['Status', selectedSession.status],
                                ['Agents', sessionAgents.length],
                                ['Executed', selectedSession.summary?.executed_count ?? 0],
                                ['Updated', formatTime(selectedUpdatedAt)],
                            ].map(([label, value]) => (
                                <div key={String(label)} className="bg-[#08080a] p-3">
                                    <p className="font-mono text-[9px] uppercase tracking-[0.15em] text-ink-tertiary">{label}</p>
                                    <p className="nums mt-1 break-words font-mono text-[12px] text-white">{String(value)}</p>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>

                <AgentChatBoard
                    runStatus={selectedSession.status_snapshot || null}
                    liveEvents={{}}
                    sessionAgents={sessionAgents}
                    activeAgent={activeAgent}
                    setActiveAgent={setActiveAgent}
                    connectionState={selectedSession.loaded_from_cloud ? 'cloud archive' : 'saved archive'}
                />
            </motion.section>
        )
    }

    return (
        <TradeHistoryArchive
            sessions={tradeSessions}
            loading={sessionsLoading}
            error={sessionsError}
            openingSessionId={openingSessionId}
            onOpenSession={openTradeSession}
            onPrefetchSession={prefetchTradeSession}
            onRetry={retryTradeSessions}
        />
    )
}

function AITradingChatContent() {
    const searchParams = useSearchParams()
    const expectedRun = searchParams.get('run')
    const requestedView = searchParams.get('view')
    const requestedSession = searchParams.get('session')
    const initialView: 'agent' | 'live' | 'trades' =
        requestedView === 'trades' || requestedSession ? 'trades' : requestedView === 'live' || expectedRun ? 'live' : 'agent'
    const [runStatus, setRunStatus] = useState<AgentRunStatus | null>(null)
    const [error, setError] = useState<string | null>(null)
    const [liveEvents, setLiveEvents] = useState<Record<number, LiveAgentEvent[]>>({})
    const [activeAgent, setActiveAgent] = useState(1)
    const [connectionState, setConnectionState] = useState('connecting')
    const [viewMode, setViewMode] = useState<'agent' | 'live' | 'trades'>(initialView)
    const [tradeSessions, setTradeSessions] = useState<TradeSessionSummary[]>([])
    const [selectedSession, setSelectedSession] = useState<TradeSession | null>(null)
    const [sessionsLoading, setSessionsLoading] = useState(initialView === 'trades')
    const [sessionsError, setSessionsError] = useState<string | null>(null)
    const [openingSessionId, setOpeningSessionId] = useState<string | null>(null)
    const bottomRef = useRef<HTMLDivElement | null>(null)
    const selectedSessionRef = useRef<TradeSession | null>(null)
    const sessionCacheRef = useRef(new Map<string, TradeSession>())
    const sessionRequestRef = useRef(new Map<string, Promise<TradeSession>>())
    const sessionsRequestRef = useRef<Promise<void> | null>(null)
    const sessionsFetchedAtRef = useRef(0)
    const statusRequestRef = useRef<Promise<void> | null>(null)
    const deepLinkedSessionRef = useRef<string | null>(null)
    const shouldAutoScrollRef = useRef(true)
    const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

    const fetchStatus = async () => {
        if (selectedSessionRef.current) return
        if (statusRequestRef.current) return statusRequestRef.current
        const request = (async () => { try {
            const response = await fetch('/api/ai-trading/toggle', { method: 'GET' })
            if (!response.ok) throw new Error('Failed to load AI trading status')
            const status = await response.json()
            setRunStatus(status)
            setError(null)
        } catch (statusError) {
            console.error('Error loading AI trading status:', statusError)
            setError('Could not load the latest agent run.')
        } finally {
            statusRequestRef.current = null
        } })()
        statusRequestRef.current = request
        return request
    }

    useEffect(() => {
        selectedSessionRef.current = selectedSession
    }, [selectedSession])

    useEffect(() => {
        if (requestedView === 'live' || expectedRun) {
            setSelectedSession(null)
            setViewMode('live')
        } else if (requestedView === 'trades' || requestedSession) {
            setViewMode('trades')
        }
    }, [requestedView, expectedRun, requestedSession])

    const fetchTradeSessions = useCallback(async (force = false) => {
        if (!force && sessionsFetchedAtRef.current && Date.now() - sessionsFetchedAtRef.current < 30_000) return
        if (sessionsRequestRef.current) return sessionsRequestRef.current
        const request = (async () => { try {
            setSessionsLoading(true)
            setSessionsError(null)
            const response = await fetch('/api/ai-trading/sessions', { method: 'GET' })
            if (!response.ok) throw new Error(`Trade history request failed (${response.status})`)
            const payload = await response.json()
            setTradeSessions(Array.isArray(payload.sessions) ? payload.sessions : [])
            sessionsFetchedAtRef.current = Date.now()
        } catch (sessionError) {
            console.error('Error loading trade sessions:', sessionError)
            setSessionsError('Trade history is temporarily unavailable. Your current screen remains usable.')
        } finally {
            setSessionsLoading(false)
            sessionsRequestRef.current = null
        } })()
        sessionsRequestRef.current = request
        return request
    }, [])

    const loadTradeSession = useCallback((sessionId: string) => {
        const cached = sessionCacheRef.current.get(sessionId)
        if (cached) return Promise.resolve(cached)
        const pending = sessionRequestRef.current.get(sessionId)
        if (pending) return pending
        const request = (async () => {
            const response = await fetch(`/api/ai-trading/sessions/${encodeURIComponent(sessionId)}`, { method: 'GET' })
            if (!response.ok) throw new Error(`Trade session request failed (${response.status})`)
            const session: TradeSession = await response.json()
            sessionCacheRef.current.set(sessionId, session)
            return session
        })().finally(() => sessionRequestRef.current.delete(sessionId))
        sessionRequestRef.current.set(sessionId, request)
        return request
    }, [])

    const prefetchTradeSession = useCallback((sessionId: string) => {
        void loadTradeSession(sessionId).catch(() => undefined)
    }, [loadTradeSession])

    const updateArchiveUrl = useCallback((view: 'agent' | 'live' | 'trades', sessionId?: string) => {
        const url = new URL(window.location.href)
        url.searchParams.set('view', view)
        if (sessionId) url.searchParams.set('session', sessionId)
        else url.searchParams.delete('session')
        if (view !== 'live') url.searchParams.delete('run')
        window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`)
    }, [])

    const openTradeSession = useCallback(async (sessionId: string) => {
        if (openingSessionId) return
        setOpeningSessionId(sessionId)
        setSessionsError(null)
        try {
            const session = await loadTradeSession(sessionId)
            setSelectedSession(session)
            setRunStatus(session.status_snapshot || null)
            setLiveEvents({})
            const firstRank = Number(session.agents?.[0]?.rank || 1)
            setActiveAgent(firstRank)
            setViewMode('trades')
            deepLinkedSessionRef.current = sessionId
            updateArchiveUrl('trades', sessionId)
            window.scrollTo({ top: 0, behavior: 'smooth' })
        } catch (sessionError) {
            console.error('Error opening trade session:', sessionError)
            setSessionsError('That run could not be opened. It may still be syncing; please try again.')
        } finally {
            setOpeningSessionId(null)
        }
    }, [loadTradeSession, openingSessionId, updateArchiveUrl])

    const resumeLiveRun = () => {
        setSelectedSession(null)
        setLiveEvents({})
        setViewMode('live')
        updateArchiveUrl('live')
        fetchStatus()
    }

    const showAgentLauncher = () => {
        setSelectedSession(null)
        setViewMode('agent')
        updateArchiveUrl('agent')
    }

    const showTradeHistory = () => {
        setSelectedSession(null)
        setViewMode('trades')
        updateArchiveUrl('trades')
        void fetchTradeSessions()
    }

    const closeTradeSession = () => {
        setSelectedSession(null)
        setLiveEvents({})
        setViewMode('trades')
        updateArchiveUrl('trades')
    }

    useEffect(() => {
        if (viewMode === 'trades') return
        void fetchStatus()
        const timer = setInterval(() => {
            if (document.visibilityState === 'visible') void fetchStatus()
        }, 8_000)
        return () => clearInterval(timer)
    }, [viewMode])

    useEffect(() => {
        if (viewMode === 'trades') {
            void fetchTradeSessions()
        }
    }, [fetchTradeSessions, viewMode])

    useEffect(() => {
        if (!requestedSession || deepLinkedSessionRef.current === requestedSession) return
        deepLinkedSessionRef.current = requestedSession
        void openTradeSession(requestedSession)
    }, [openTradeSession, requestedSession])

    useEffect(() => {
        if (viewMode !== 'live') {
            setConnectionState('paused')
            return
        }
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
                        setLiveEvents((current) => {
                            const existing = current[rank] || []
                            const isDuplicate = payload.sequence !== undefined && existing.some(
                                (item) => item.sequence === Number(payload.sequence) && item.type === payload.type,
                            )
                            if (isDuplicate) return current
                            return {
                                ...current,
                                [rank]: [
                                    ...existing,
                                    {
                                        ...payload,
                                        rank,
                                        sequence: payload.sequence !== undefined ? Number(payload.sequence) : undefined,
                                    } as LiveAgentEvent,
                                ],
                            }
                        })
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
    }, [viewMode])

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
        <div className="product-shell relative min-h-screen bg-[#050505] text-white overflow-x-hidden">
            {/* Ambient backdrop */}
            <div className="pointer-events-none fixed inset-0 bg-grid-fine opacity-50" />
            <div className="pointer-events-none fixed inset-0 bg-spotlight" />

            <header className="sticky top-0 z-40">
                <div className="mx-auto max-w-7xl px-4 pt-4 sm:px-6">
                    <div className="glass flex flex-col justify-between gap-3 rounded-2xl px-4 py-3 sm:flex-row sm:items-center sm:rounded-full sm:px-6">
                        <div className="flex min-w-0 items-center gap-3 sm:gap-4">
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
                                    {viewMode === 'agent' ? 'Trading settings' : viewMode === 'trades' ? 'Trade history' : 'Live events'}
                                </p>
                                <h1 className="font-display text-[18px] sm:text-[20px] text-white tracking-[-0.02em] leading-[1.1] mt-0.5">
                                    AI Trading <span className="font-serif-italic text-ink-secondary">{viewMode === 'agent' ? 'Control' : viewMode === 'trades' ? 'Archive' : 'Workspace'}</span>
                                </h1>
                            </div>
                        </div>
                        <nav className="no-scrollbar flex w-full items-center gap-2 overflow-x-auto sm:w-auto" aria-label="AI trading navigation">
                            <button
                                type="button"
                                onClick={showAgentLauncher}
                                className={`flex-shrink-0 rounded-full border px-4 py-2 font-mono text-[10px] uppercase tracking-[0.14em] transition-colors ${viewMode === 'agent' ? 'border-accent/40 bg-accent/[0.09] text-white' : 'border-line bg-white/[0.03] text-ink-secondary hover:text-white'}`}
                            >
                                Amount
                            </button>
                            <button
                                type="button"
                                onClick={resumeLiveRun}
                                className={`flex-shrink-0 rounded-full border px-4 py-2 font-mono text-[10px] uppercase tracking-[0.14em] transition-colors ${viewMode === 'live' ? 'border-warning/40 bg-warning/[0.08] text-white' : 'border-line bg-white/[0.03] text-ink-secondary hover:text-white'}`}
                            >
                                Live run {rows.length > 1 ? `· ${rows.length}` : ''}
                            </button>
                            <button
                                type="button"
                                onClick={showTradeHistory}
                                className={`flex-shrink-0 rounded-full border px-4 py-2 font-mono text-[10px] uppercase tracking-[0.14em] transition-colors ${viewMode === 'trades' ? 'border-success/50 bg-success/[0.08] text-white' : 'border-line bg-white/[0.03] text-ink-secondary hover:text-white'}`}
                            >
                                Trades
                            </button>
                            <Link href="/dashboard" className="flex-shrink-0 rounded-full border border-line bg-white/[0.03] px-4 py-2 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-secondary transition-colors hover:text-white">
                                Dashboard
                            </Link>
                        </nav>
                    </div>
                </div>
            </header>

            <main className="relative mx-auto max-w-7xl px-4 pb-24 pt-8 sm:px-6 lg:px-8">
                {viewMode === 'live' && (
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
                )}

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

                {viewMode === 'agent' ? (
                    <section className="mx-auto max-w-3xl">
                        <div className="mb-7 text-center">
                            <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-accent">
                                Trading amount
                            </p>
                            <h2 className="mt-3 text-[32px] font-semibold tracking-[-0.045em] text-white sm:text-[46px]">
                                Choose fixed or automatic sizing.
                            </h2>
                            <p className="mx-auto mt-3 max-w-xl text-[13px] leading-relaxed text-ink-secondary">
                                Leave the amount blank to use available balance automatically, or enter a fixed amount. The scanner and Intra-Finder monitor continuously; no manual start is required.
                            </p>
                        </div>
                        <TradingStatus />
                    </section>
                ) : viewMode === 'trades' ? (
                    <TradeHistoryView
                        tradeSessions={tradeSessions}
                        selectedSession={selectedSession}
                        openTradeSession={openTradeSession}
                        prefetchTradeSession={prefetchTradeSession}
                        closeTradeSession={closeTradeSession}
                        activeAgent={activeAgent}
                        setActiveAgent={setActiveAgent}
                        sessionsLoading={sessionsLoading}
                        openingSessionId={openingSessionId}
                        sessionsError={sessionsError}
                        retryTradeSessions={() => void fetchTradeSessions(true)}
                    />
                ) : (
                    <div className="space-y-5 pb-8">
                    <AgentChatBoard
                        runStatus={runStatus}
                        liveEvents={liveEvents}
                        sessionAgents={[]}
                        activeAgent={activeAgent}
                        setActiveAgent={setActiveAgent}
                        connectionState={connectionState}
                    />

                    {false && messages.map(({ stage, data }, index) => {
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

                    {false && runStatus?.status === 'completed' && (
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
            <div className="product-shell min-h-screen bg-[#050505] flex items-center justify-center">
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
