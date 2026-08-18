'use client'

import { Suspense, useCallback, useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import TradingStatus from '@/components/trading-status'
import { AgentConsole } from '@/components/agent/agent-console'
import { RunSummary } from '@/components/agent/run-summary'
import { useAgentRunContext } from '@/components/agent/agent-run-provider'
import type { AgentView } from '@/components/ai-trading/types'
import { Notice } from '@/components/ui/notice'
import { CellGrid, Panel } from '@/components/ui/panel'
import { Skeleton } from '@/components/ui/skeleton'
import { SegmentedTabs, type TabItem } from '@/components/ui/tabs'
import { Reveal } from '@/components/motion/reveal'
import { ViewSlide } from '@/components/motion/view-slide'

const TABS: TabItem<AgentView>[] = [
    { id: 'live', label: 'Live run' },
    { id: 'sizing', label: 'Trade sizing' },
]

const VIEW_PANEL_ID = 'agent-view-panel'

/** `agent` was the old name for the sizing view; keep old links working. */
function viewFromParam(value: string | null): AgentView {
    return value === 'sizing' || value === 'agent' ? 'sizing' : 'live'
}

function AgentPageContent() {
    const router = useRouter()
    const searchParams = useSearchParams()
    const requestedView = searchParams.get('view')
    const legacySession = searchParams.get('session')
    const [view, setView] = useState<AgentView>(() => viewFromParam(requestedView))

    // Trade history used to be a third mode of this page. Forward the old
    // query-string entry points to the route that now owns it.
    useEffect(() => {
        if (requestedView !== 'trades' && !legacySession) return
        router.replace(
            legacySession ? `/dashboard/trades?session=${encodeURIComponent(legacySession)}` : '/dashboard/trades',
        )
    }, [requestedView, legacySession, router])

    const { status, events, stream, error } = useAgentRunContext()

    const changeView = useCallback((next: AgentView) => {
        setView(next)
        const url = new URL(window.location.href)
        url.searchParams.set('view', next)
        window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}`)
    }, [])

    return (
        <>
            <header className="mb-6 flex flex-col justify-between gap-5 md:flex-row md:items-end">
                <Reveal immediate>
                    <p className="dash-label mb-2">Autonomous execution</p>
                    <h1 className="text-[28px] font-medium leading-none tracking-[-0.04em] text-ink-primary sm:text-[34px]">
                        Agent
                    </h1>
                    <p className="mt-2.5 max-w-xl text-[12px] leading-relaxed text-ink-tertiary">
                        The scanner and Intra-Finder monitor the market continuously. Runs start on their own; this is
                        where you watch them and set how much capital each trade may use.
                    </p>
                </Reveal>
                <SegmentedTabs
                    items={TABS}
                    value={view}
                    onChange={changeView}
                    ariaLabel="Agent views"
                    panelId={VIEW_PANEL_ID}
                />
            </header>

            {error && (
                <Notice tone="warning" className="mb-4">
                    {error}
                </Notice>
            )}

            <div id={VIEW_PANEL_ID} role="tabpanel" aria-labelledby={`tab-${view}`}>
                {/* The tab pill has already shown which way the reader moved;
                    the panel travels the same direction so the two agree. */}
                <ViewSlide index={view === 'live' ? 0 : 1}>
                    {view === 'live' ? (
                        <div className="space-y-4">
                            <RunSummary status={status} />
                            <AgentConsole runStatus={status} liveEvents={events} stream={stream} />
                        </div>
                    ) : (
                        <div className="max-w-2xl">
                            <TradingStatus />
                        </div>
                    )}
                </ViewSlide>
            </div>
        </>
    )
}

function AgentFallback() {
    return (
        <>
            <div className="mb-6">
                <Skeleton className="h-2.5 w-36" />
                <Skeleton className="mt-3 h-8 w-32" />
                <Skeleton className="mt-3 h-2.5 w-80" />
            </div>
            <CellGrid className="grid-cols-2 lg:grid-cols-4">
                {[0, 1, 2, 3].map((item) => (
                    <div key={item} className="px-4 py-3.5">
                        <Skeleton className="h-2.5 w-20" />
                        <Skeleton className="mt-3 h-3.5 w-24" />
                    </div>
                ))}
            </CellGrid>
            <Panel className="mt-4">
                <div className="panel-body">
                    <Skeleton className="h-48 w-full" />
                </div>
            </Panel>
        </>
    )
}

export default function AgentPage() {
    return (
        <Suspense fallback={<AgentFallback />}>
            <AgentPageContent />
        </Suspense>
    )
}
