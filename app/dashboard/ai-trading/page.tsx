'use client'

import { Suspense, useEffect, useMemo, useRef, useState } from 'react'
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

const stageLabels: Record<string, string> = {
    stage2: 'Stage 2 Momentum',
    stock_analyzer: 'Stock Analyzer',
    executioner: 'Executioner',
}

const stageOrder = ['stage2', 'stock_analyzer', 'executioner']

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
                <p className="text-[12px] text-ink-secondary font-mono">
                    Selected: {(data.summary?.selected_symbols || []).join(', ') || 'No symbols found'}
                </p>
                {reports.map((report: any) => (
                    <div key={`${report.rank}-${report.symbol}`} className="pt-3 border-t border-line/60 first:border-t-0 first:pt-0">
                        <p className="text-success font-mono text-[10px] uppercase tracking-[0.18em]">
                            #{report.rank} {report.display_name || report.symbol}
                        </p>
                        <p className="text-[13px] text-ink-secondary mt-2 whitespace-pre-wrap leading-relaxed">
                            {report.analysis}
                        </p>
                    </div>
                ))}
            </div>
        )
    }

    const executionResults = data.details?.results || []
    if (stage === 'executioner' && executionResults.length > 0) {
        return (
            <div className="space-y-3">
                {executionResults.map((result: any) => (
                    <div key={`${result.rank}-${result.display_name}`} className="pt-3 border-t border-line/60 first:border-t-0 first:pt-0">
                        <p className="text-success font-mono text-[10px] uppercase tracking-[0.18em]">
                            #{result.rank} {result.display_name || 'Stock'}
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
                        <p className="text-[13px] text-ink-secondary mt-3 whitespace-pre-wrap leading-relaxed">
                            {result.report_text}
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

    const isRunning = runStatus?.status === 'running'
    const statusAccent = isRunning ? 'text-warning' : runStatus?.status === 'completed' ? 'text-success' : 'text-accent'

    return (
        <div className="relative min-h-screen bg-[#050505] text-white overflow-x-hidden">
            {/* Ambient backdrop */}
            <div className="pointer-events-none fixed inset-0 bg-grid-fine opacity-50" />
            <div className="pointer-events-none fixed inset-0 bg-spotlight" />

            {/* Header */}
            <header className="sticky top-0 z-40">
                <div className="mx-auto max-w-6xl px-4 sm:px-6 pt-5">
                    <div className="glass rounded-full px-5 sm:px-6 py-3 flex items-center justify-between gap-4">
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
                                    Live Agent Run
                                </p>
                                <h1 className="font-display text-[18px] sm:text-[20px] text-white tracking-[-0.02em] leading-[1.1] mt-0.5">
                                    AI Trading <span className="font-serif-italic text-ink-secondary">Terminal</span>
                                </h1>
                            </div>
                        </div>
                        <Link href="/dashboard" className="btn-secondary !px-4 !py-1.5 !text-[12px] flex-shrink-0">
                            Dashboard
                        </Link>
                    </div>
                </div>
            </header>

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

                {/* Conversation stream */}
                <div className="space-y-5 pb-8">
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
                                Run the trading agents once, in order, only after Stage 2 is ready.
                            </p>
                        </div>
                    </motion.div>

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
