'use client'

import { Suspense, useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { CapitalControl } from '@/components/agent/capital-control'
import { AgentConsole } from '@/components/agent/agent-console'
import { RunSummary } from '@/components/agent/run-summary'
import { useAgentRunContext } from '@/components/agent/agent-run-provider'
import { Notice } from '@/components/ui/notice'
import { CellGrid, Panel } from '@/components/ui/panel'
import { Skeleton } from '@/components/ui/skeleton'
import { Reveal } from '@/components/motion/reveal'

/**
 * Agent — one screen, one job: watch the run, and see the limit it trades under.
 *
 * This page used to be two tabbed views, "Live run" and "Trade sizing". The tab
 * rail is gone and so is the second view. A tab rail claims its options are peer
 * views of equal standing, and these were not: one is a continuously updating
 * feed, the other is a single setting. Worse, the split meant the run and the
 * capital limit governing it were never visible at the same time, so answering
 * "how much can this thing spend" cost a navigation.
 *
 * The setting is now a row at the top that opens in place, above the run it
 * applies to. Two levels of tabs on one screen are also gone, since the console
 * below already switches between the roster and an individual agent.
 *
 * Legacy entry points still resolve: `?view=sizing` and `?view=agent` land here
 * and simply have nothing left to switch, and `?view=trades` or a bare
 * `?session=` still forwards to the route that owns trade history.
 */
function AgentPageContent() {
    const router = useRouter()
    const searchParams = useSearchParams()
    const requestedView = searchParams.get('view')
    const legacySession = searchParams.get('session')

    // Trade history used to be a third mode of this page. Forward the old
    // query-string entry points to the route that now owns it.
    useEffect(() => {
        if (requestedView !== 'trades' && !legacySession) return
        router.replace(
            legacySession ? `/dashboard/trades?session=${encodeURIComponent(legacySession)}` : '/dashboard/trades',
        )
    }, [requestedView, legacySession, router])

    const { status, events, stream, error } = useAgentRunContext()

    return (
        <>
            <Reveal immediate as="header" className="mb-6">
                <p className="dash-label mb-2">Autonomous execution</p>
                <h1 className="section-title">Agent</h1>
                <p className="section-lede">
                    The scanner and Intra-Finder watch the market continuously, so runs start on their own. This is
                    where you follow one and set the capital it may commit.
                </p>
            </Reveal>

            {error && (
                <Notice tone="warning" className="mb-4">
                    {error}
                </Notice>
            )}

            <div className="space-y-4">
                <CapitalControl />
                <RunSummary status={status} />
                <AgentConsole runStatus={status} liveEvents={events} stream={stream} />
            </div>
        </>
    )
}

/** Mirrors the loaded layout so nothing jumps into place. */
function AgentFallback() {
    return (
        <>
            <div className="mb-6">
                <Skeleton className="h-2.5 w-36" />
                <Skeleton className="mt-3 h-8 w-32" delay={40} />
                <Skeleton className="mt-3 h-2.5 w-80 max-w-full" delay={80} />
            </div>
            <div className="space-y-4">
                <Panel>
                    <div className="flex items-center gap-3 px-4 py-3.5 sm:px-5">
                        <Skeleton className="h-4 w-4 rounded" />
                        <div className="min-w-0 flex-1">
                            <Skeleton className="h-3 w-40" />
                            <Skeleton className="mt-2 h-2.5 w-64 max-w-full" delay={40} />
                        </div>
                    </div>
                </Panel>
                <CellGrid className="grid-cols-2 lg:grid-cols-4">
                    {[0, 1, 2, 3].map((item) => (
                        <div key={item} className="px-4 py-3.5">
                            <Skeleton className="h-2.5 w-20" delay={item * 40} />
                            <Skeleton className="mt-3 h-3.5 w-24" delay={item * 40} />
                        </div>
                    ))}
                </CellGrid>
                <Panel>
                    <div className="panel-body">
                        <Skeleton className="h-48 w-full" />
                    </div>
                </Panel>
            </div>
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
