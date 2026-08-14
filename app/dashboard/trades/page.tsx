'use client'

import { Suspense, useCallback, useEffect } from 'react'
import { useSearchParams } from 'next/navigation'
import { SessionDetail } from '@/components/trades/session-detail'
import { TradeArchive } from '@/components/trades/trade-archive'
import { useTradeSessions } from '@/components/trades/use-trade-sessions'
import { Notice } from '@/components/ui/notice'
import { CellGrid, Panel } from '@/components/ui/panel'
import { Skeleton } from '@/components/ui/skeleton'

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

    // Keep the URL in step with the open run so it can be shared or reloaded.
    useEffect(() => {
        const url = new URL(window.location.href)
        if (selected) url.searchParams.set('session', selected.session_id)
        else url.searchParams.delete('session')
        window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}`)
    }, [selected])

    const open = useCallback((sessionId: string) => void openSession(sessionId), [openSession])

    return (
        <>
            <header className="mb-6">
                <p className="dash-label mb-2">History</p>
                <h1 className="text-[28px] font-medium leading-none tracking-[-0.04em] text-ink-primary sm:text-[34px]">
                    Trades
                </h1>
                <p className="mt-2.5 max-w-xl text-[12px] leading-relaxed text-ink-tertiary">
                    Every archived agent run, grouped by trading day. Open a run for its decision, the charts it was
                    made from, and the full event log.
                </p>
            </header>

            {detailError && (
                <Notice tone="danger" className="mb-4">
                    {detailError}
                </Notice>
            )}

            {selected ? (
                <SessionDetail session={selected} onBack={closeSession} />
            ) : (
                <TradeArchive
                    sessions={sessions}
                    loading={listLoading}
                    error={listError}
                    openingId={openingId}
                    onOpen={open}
                    onPrefetch={prefetchSession}
                    onRetry={() => void reload()}
                />
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
                        <Skeleton className="h-2.5 w-20" />
                        <Skeleton className="mt-4 h-5 w-16" />
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
