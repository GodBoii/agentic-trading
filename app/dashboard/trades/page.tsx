'use client'

import { Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { SessionDetail } from '@/components/trades/session-detail'
import { TradeArchive } from '@/components/trades/trade-archive'
import { useTradeSessions } from '@/components/trades/use-trade-sessions'
import { Notice } from '@/components/ui/notice'
import { CellGrid, Panel } from '@/components/ui/panel'
import { Skeleton } from '@/components/ui/skeleton'
import { Reveal } from '@/components/motion/reveal'

/**
 * Trade history, now a route of its own.
 *
 * This was previously a third view mode inside `/dashboard/ai-trading`, reached
 * through `?view=trades` and switched with `history.replaceState`. As a real
 * route it gets browser history, a shareable URL, and its own header state.
 */
function TradesPageContent() {
    const searchParams = useSearchParams()
    const deepLinkedSession = searchParams.get('session')

    const {
        sessions,
        listLoading,
        listError,
        selected,
        openingId,
        detailError,
        reload,
        openSession,
        prefetchSession,
        closeSession,
    } = useTradeSessions(deepLinkedSession)

    /**
     * Opening a run pushes a history entry, so the phone's back gesture and the
     * browser back button return to the list instead of leaving Trades.
     * `pushedFor` remembers which run this page pushed, so the in-page back
     * button can pop that entry rather than stacking another one.
     */
    const pushedFor = useRef<string | null>(null)
    const listScroll = useRef(0)

    useEffect(() => {
        if (!selected) return
        const url = new URL(window.location.href)
        if (url.searchParams.get('session') === selected.session_id) return
        url.searchParams.set('session', selected.session_id)
        pushedFor.current = selected.session_id
        window.history.pushState(null, '', `${url.pathname}${url.search}`)
    }, [selected])

    // Back (gesture, button or in-page) removes `?session`. Close the run when
    // the param goes from set to unset; a forward navigation that sets it again
    // is picked up by the deep-link effect inside `useTradeSessions`.
    const previousParam = useRef(deepLinkedSession)
    useEffect(() => {
        const had = previousParam.current
        previousParam.current = deepLinkedSession
        if (had && !deepLinkedSession && selected) {
            pushedFor.current = null
            closeSession()
        }
    }, [deepLinkedSession, selected, closeSession])

    // The list stays mounted while a run is open, so search, the open day and
    // the scroll position all survive the round trip. Scroll is restored here.
    const wasOpen = useRef(false)
    useEffect(() => {
        if (selected) {
            wasOpen.current = true
            return
        }
        if (!wasOpen.current) return
        wasOpen.current = false
        const top = listScroll.current
        requestAnimationFrame(() => window.scrollTo({ top }))
    }, [selected])

    // The list only plays its return slide after a run has been opened;
    // on first load the route entrance already covers it.
    const [openedOnce, setOpenedOnce] = useState(false)
    const open = useCallback(
        (sessionId: string) => {
            listScroll.current = window.scrollY
            setOpenedOnce(true)
            void openSession(sessionId)
        },
        [openSession],
    )

    const back = useCallback(() => {
        if (selected && pushedFor.current === selected.session_id) {
            window.history.back()
            return
        }
        // Arrived by deep link: there is no list entry behind this one to pop.
        pushedFor.current = null
        closeSession()
        const url = new URL(window.location.href)
        url.searchParams.delete('session')
        window.history.replaceState(null, '', `${url.pathname}${url.search}`)
    }, [selected, closeSession])

    return (
        <>
            <Reveal immediate as="header" className="mb-6">
                <h1 className="section-title">Trades</h1>
                <p className="section-lede">
                    Every archived agent run by trading day, with what each agent read, its reasoning and its charts.
                </p>
            </Reveal>

            {detailError && (
                <Notice tone="danger" className="mb-4">
                    {detailError}
                </Notice>
            )}

            {/* List and detail are a pair: the detail slides in from the
                right, the list back from the left. The list is hidden rather
                than unmounted so its state survives. */}
            <div hidden={Boolean(selected)} className={openedOnce ? 'view-in-prev' : undefined}>
                <TradeArchive
                    sessions={sessions}
                    loading={listLoading}
                    error={listError}
                    openingId={openingId}
                    onOpen={open}
                    onPrefetch={prefetchSession}
                    onRetry={() => void reload()}
                />
            </div>
            {selected && (
                <div key={selected.session_id} className="view-in-next">
                    <SessionDetail session={selected} onBack={back} />
                </div>
            )}
        </>
    )
}

function TradesFallback() {
    return (
        <>
            <div className="mb-6">
                <Skeleton className="h-2.5 w-24" />
                <Skeleton className="mt-3 h-8 w-36" />
                <Skeleton className="mt-3 h-2.5 w-80" />
            </div>
            <CellGrid className="grid-cols-2 lg:grid-cols-4">
                {[0, 1, 2, 3].map((item) => (
                    <div key={item} className="p-5">
                        <Skeleton className="h-2.5 w-20" delay={item * 40} />
                        <Skeleton className="mt-4 h-5 w-16" delay={item * 40} />
                    </div>
                ))}
            </CellGrid>
            <Panel className="mt-4">
                <div className="panel-body">
                    <Skeleton className="h-24 w-full" />
                </div>
            </Panel>
        </>
    )
}

export default function TradesPage() {
    return (
        <Suspense fallback={<TradesFallback />}>
            <TradesPageContent />
        </Suspense>
    )
}
