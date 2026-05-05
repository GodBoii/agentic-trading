'use client'

import { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'

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

const stageLabels: Record<string, string> = {
    stage2: 'Stage 2 Momentum',
    stock_analyzer: 'Stock Analyzer',
    risk_analyzer: 'Risk Analyzer',
    executioner: 'Executioner',
}

const stageOrder = ['stage2', 'stock_analyzer', 'risk_analyzer', 'executioner']

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

    if (stage === 'stock_analyzer') {
        const reports = data.details?.reports || []
        return (
            <div className="space-y-3">
                <p className="text-sm text-brutal-cream/80 font-mono">
                    Selected: {(data.summary?.selected_symbols || []).join(', ') || 'No symbols found'}
                </p>
                {reports.map((report: any) => (
                    <div key={`${report.rank}-${report.symbol}`} className="border-t-3 border-brutal-cream/10 pt-3">
                        <p className="text-brutal-green font-mono text-xs font-bold uppercase">
                            #{report.rank} {report.display_name || report.symbol}
                        </p>
                        <p className="text-sm text-brutal-cream/75 mt-2 whitespace-pre-wrap">
                            {report.analysis}
                        </p>
                    </div>
                ))}
            </div>
        )
    }

    const decision = data.details?.decision || {}
    return (
        <div className="space-y-3">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {Object.entries(decision).slice(0, 8).map(([key, value]) => (
                    <div key={key} className="border-3 border-brutal-cream/20 p-3">
                        <p className="text-[10px] text-brutal-cream/50 font-mono uppercase">{key.replaceAll('_', ' ')}</p>
                        <p className="text-sm text-brutal-cream font-mono font-bold break-words">{String(value)}</p>
                    </div>
                ))}
            </div>
            <p className="text-sm text-brutal-cream/75 whitespace-pre-wrap">
                {data.details?.report_text}
            </p>
        </div>
    )
}

function AITradingChatContent() {
    const searchParams = useSearchParams()
    const expectedRun = searchParams.get('run')
    const [runStatus, setRunStatus] = useState<AgentRunStatus | null>(null)
    const [error, setError] = useState<string | null>(null)
    const bottomRef = useRef<HTMLDivElement | null>(null)
    const shouldAutoScrollRef = useRef(true)

    const fetchStatus = async () => {
        try {
            const response = await fetch('/api/ai-trading/toggle', { method: 'GET' })
            if (!response.ok) throw new Error('Failed to load AI trading status')
            setRunStatus(await response.json())
            setError(null)
        } catch (statusError) {
            console.error('Error loading AI trading status:', statusError)
            setError('Could not load the latest agent run.')
        }
    }

    useEffect(() => {
        fetchStatus()
        const timer = setInterval(fetchStatus, 2500)
        return () => clearInterval(timer)
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
        return stageOrder.map((stage) => ({
            stage,
            data: stages[stage],
        }))
    }, [runStatus])

    return (
        <div className="min-h-screen bg-brutal-black overflow-hidden">
            <div className="fixed inset-0 pointer-events-none animate-dashboard-to-chat">
                <div className="absolute inset-x-8 top-8 h-24 border-4 border-brutal-cream/20"></div>
                <div className="absolute left-8 right-8 bottom-8 h-20 border-4 border-brutal-green/20"></div>
            </div>

            <header className="border-b-4 border-brutal-white bg-brutal-black sticky top-0 z-40">
                <div className="max-w-6xl mx-auto px-6 py-5 flex items-center justify-between gap-4">
                    <div>
                        <p className="text-xs text-brutal-green font-mono font-bold uppercase tracking-widest">
                            Live Agent Run
                        </p>
                        <h1 className="text-3xl md:text-4xl text-brutal-cream font-bold uppercase tracking-tight">
                            AI Trading Chat
                        </h1>
                    </div>
                    <Link href="/dashboard" className="brutal-btn px-5 py-3 text-xs">
                        Dashboard
                    </Link>
                </div>
            </header>

            <main className="max-w-6xl mx-auto px-6 py-8">
                <div className="mb-6 brutal-box-sm border-brutal-green shadow-none p-5 animate-chat-rise">
                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
                        <div>
                            <p className="text-xs text-brutal-cream/50 font-mono uppercase">Run ID</p>
                            <p className="text-sm text-brutal-cream font-mono break-all">
                                {runStatus?.request?.request_id || expectedRun || 'Waiting for request'}
                            </p>
                        </div>
                        <div className="text-left md:text-right">
                            <p className="text-xs text-brutal-cream/50 font-mono uppercase">Status</p>
                            <p className="text-lg text-brutal-green font-mono font-bold uppercase">
                                {runStatus?.status || 'loading'}
                            </p>
                        </div>
                    </div>
                    {runStatus?.message && (
                        <p className="mt-4 text-sm text-brutal-yellow font-mono font-bold uppercase">
                            {runStatus.message}
                        </p>
                    )}
                </div>

                {error && (
                    <div className="mb-6 brutal-box-sm border-brutal-red shadow-brutal-red p-4">
                        <p className="text-brutal-red font-mono text-sm font-bold uppercase">{error}</p>
                    </div>
                )}

                <div className="space-y-5 pb-8">
                    <div className="flex justify-end animate-chat-rise">
                        <div className="max-w-3xl border-4 border-brutal-green bg-brutal-green text-brutal-black p-5">
                            <p className="font-mono text-sm font-bold uppercase">Start AI Trading</p>
                            <p className="text-sm mt-2">
                                Run the trading agents once, in order, only after Stage 2 is ready.
                            </p>
                        </div>
                    </div>

                    {messages.map(({ stage, data }, index) => {
                        const active = data?.status === 'running'
                        const complete = data?.status === 'completed'
                        return (
                            <div
                                key={stage}
                                className="flex justify-start animate-chat-rise"
                                style={{ animationDelay: `${index * 90}ms` }}
                            >
                                <div className={`max-w-4xl w-full border-4 p-5 ${complete ? 'border-brutal-green' : active ? 'border-brutal-yellow' : 'border-brutal-cream/30'}`}>
                                    <div className="flex items-start justify-between gap-4 mb-3">
                                        <div className="flex items-center gap-3">
                                            <div className={`w-4 h-4 ${complete ? 'bg-brutal-green' : active ? 'bg-brutal-yellow' : 'bg-brutal-cream/30'}`}></div>
                                            <div>
                                                <p className="text-brutal-cream font-bold uppercase tracking-tight">
                                                    {stageLabels[stage]}
                                                </p>
                                                <p className="text-xs text-brutal-cream/50 font-mono uppercase">
                                                    {data?.status || 'pending'}
                                                </p>
                                            </div>
                                        </div>
                                        <p className="text-xs text-brutal-cream/50 font-mono">
                                            {formatTime(data?.generated_at_utc)}
                                        </p>
                                    </div>
                                    <p className="text-sm text-brutal-cream/80 mb-4">
                                        {statusText(stage, data)}
                                    </p>
                                    {stageBody(stage, data)}
                                </div>
                            </div>
                        )
                    })}

                    {runStatus?.error && (
                        <div className="flex justify-start animate-chat-rise">
                            <div className="max-w-4xl w-full border-4 border-brutal-red p-5">
                                <p className="text-brutal-red font-mono font-bold uppercase">Run failed</p>
                                <p className="text-sm text-brutal-cream/80 mt-2">{runStatus.error}</p>
                            </div>
                        </div>
                    )}
                    <div ref={bottomRef}></div>
                </div>
            </main>
        </div>
    )
}

export default function AITradingChatPage() {
    return (
        <Suspense fallback={<div className="min-h-screen bg-brutal-black text-brutal-cream p-8 font-mono">Loading AI trading chat...</div>}>
            <AITradingChatContent />
        </Suspense>
    )
}
