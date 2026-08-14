'use client'

import { useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { useGSAP } from '@gsap/react'
import { TradeDateCard } from './trade-date-card'
import type { TradeSessionSummary } from './types'
import { groupSessionsByDate } from './utils'

gsap.registerPlugin(ScrollTrigger, useGSAP)

export function TradeHistoryArchive({
    sessions,
    loading,
    error,
    openingSessionId,
    onOpenSession,
    onPrefetchSession,
    onRetry,
}: {
    sessions: TradeSessionSummary[]
    loading: boolean
    error: string | null
    openingSessionId: string | null
    onOpenSession: (sessionId: string) => void
    onPrefetchSession: (sessionId: string) => void
    onRetry: () => void
}) {
    const archiveRef = useRef<HTMLElement | null>(null)
    const [openDateKey, setOpenDateKey] = useState<string | null>(null)
    const dateGroups = useMemo(() => groupSessionsByDate(sessions), [sessions])

    useGSAP(() => {
        if (loading || !dateGroups.length) return
        if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
            gsap.set(['.trade-date-card', '.trade-hero-word'], { clearProps: 'all' })
            return
        }
        gsap.utils.toArray<HTMLElement>('.trade-date-card').forEach((card, index) => {
            gsap.fromTo(card, { autoAlpha: 0, y: 20, scale: 0.99 }, {
                autoAlpha: 1,
                y: 0,
                scale: 1,
                duration: 0.5,
                delay: Math.min(index, 4) * 0.04,
                ease: 'power3.out',
                scrollTrigger: { trigger: card, start: 'top 94%', once: true },
            })
        })
        gsap.fromTo('.trade-hero-word', { opacity: 0.22 }, {
            opacity: 1,
            stagger: 0.08,
            ease: 'none',
            scrollTrigger: {
                trigger: '.trade-archive-hero',
                start: 'top 85%',
                end: 'bottom 48%',
                scrub: 0.35,
            },
        })
    }, { scope: archiveRef, dependencies: [loading, dateGroups.length] })

    return (
        <section ref={archiveRef}>
            <ArchiveHero runCount={sessions.length} dayCount={dateGroups.length} />
            {error && <ArchiveError message={error} onRetry={onRetry} />}

            {loading && sessions.length === 0 ? (
                <ArchiveSkeleton />
            ) : sessions.length === 0 ? (
                <ArchiveEmptyState />
            ) : (
                <div className="grid grid-flow-dense grid-cols-1 gap-4">
                    {dateGroups.map((group) => (
                        <TradeDateCard
                            key={group.key}
                            group={group}
                            open={openDateKey === group.key}
                            openingSessionId={openingSessionId}
                            onToggle={() => setOpenDateKey((current) => current === group.key ? null : group.key)}
                            onOpenSession={onOpenSession}
                            onPrefetchSession={onPrefetchSession}
                        />
                    ))}
                </div>
            )}
        </section>
    )
}

function ArchiveHero({ runCount, dayCount }: { runCount: number; dayCount: number }) {
    return (
        <div className="trade-archive-hero relative mb-10 overflow-hidden rounded-[28px] border border-white/[0.08] bg-[linear-gradient(135deg,rgba(255,255,255,0.045),rgba(255,255,255,0.012))] px-5 py-8 sm:px-8 sm:py-10 lg:px-10">
            <div className="pointer-events-none absolute -right-24 -top-36 h-80 w-80 rounded-full bg-accent/[0.08] blur-[100px]" />
            <div className="relative flex flex-col justify-between gap-8 lg:flex-row lg:items-end">
                <div className="max-w-5xl">
                    <h2 className="font-grotesk text-[clamp(2.6rem,6vw,5.8rem)] font-medium leading-[0.9] tracking-[-0.065em] text-white">
                        <span className="trade-hero-word">Your </span>
                        <span className="trade-hero-word font-serif-italic text-white/55">trading memory,</span>
                        <span className="trade-hero-word"> organized by day.</span>
                    </h2>
                    <p className="mt-6 max-w-2xl text-[14px] leading-relaxed text-ink-secondary sm:text-[15px]">
                        Open a trading day to browse its agent sessions, then select a run for the complete analysis, charts, artifacts, and response trail.
                    </p>
                </div>
                <div className="flex items-end gap-7 border-l border-white/10 pl-5 lg:min-w-[220px]">
                    <ArchiveMetric value={runCount} label="Runs" />
                    <ArchiveMetric value={dayCount} label="Trading days" />
                </div>
            </div>
        </div>
    )
}

function ArchiveMetric({ value, label }: { value: number; label: string }) {
    return <div><p className="nums text-[32px] font-medium tracking-[-0.05em] text-white">{value}</p><p className="mt-1 font-mono text-[9px] uppercase tracking-[0.16em] text-ink-tertiary">{label}</p></div>
}

function ArchiveError({ message, onRetry }: { message: string; onRetry: () => void }) {
    return <div className="mb-4 flex flex-col justify-between gap-3 rounded-2xl border border-danger/30 bg-danger/[0.055] px-4 py-3 sm:flex-row sm:items-center"><p className="text-[12px] text-danger">{message}</p><button type="button" onClick={onRetry} className="archive-retry-button self-start rounded-full border border-danger/35 px-3 py-1.5 font-mono text-[9px] uppercase tracking-[0.14em] text-white sm:self-auto">Try again</button></div>
}

function ArchiveSkeleton() {
    return <div className="min-h-[440px]" aria-label="Loading trade history"><div className="grid gap-4">{[0, 1, 2].map((item) => <div key={item} className="archive-skeleton h-[132px] rounded-[26px] border border-white/[0.06] bg-white/[0.025]" />)}</div></div>
}

function ArchiveEmptyState() {
    return <div className="surface grid min-h-[420px] place-items-center rounded-3xl border border-dashed border-line"><div className="text-center"><p className="text-[15px] font-medium text-white">No saved agent runs yet</p><Link href="/dashboard/ai-trading" className="mt-3 inline-flex text-[13px] text-accent hover:underline">Return to trading controls</Link></div></div>
}
