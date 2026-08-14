'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import type { TradeSession } from '@/components/ai-trading/types'
import type { TradeSessionSummary } from './types'

/** The list is cheap to re-request but rarely changes mid-session. */
const LIST_TTL_MS = 30_000

/**
 * Trade history data access: the session list plus lazily-loaded detail.
 *
 * Caching is deliberate rather than incidental. Opening a run, going back, and
 * opening it again is the dominant navigation pattern here, and each detail
 * request reassembles a full run from `agno_sessions` server-side — so results
 * are cached per session id and concurrent requests for the same id share one
 * promise.
 */
export function useTradeSessions(initialSessionId?: string | null) {
    const [sessions, setSessions] = useState<TradeSessionSummary[]>([])
    const [listLoading, setListLoading] = useState(true)
    const [listError, setListError] = useState<string | null>(null)

    const [selected, setSelected] = useState<TradeSession | null>(null)
    const [openingId, setOpeningId] = useState<string | null>(null)
    const [detailError, setDetailError] = useState<string | null>(null)

    const listRequest = useRef<Promise<void> | null>(null)
    const listFetchedAt = useRef(0)
    const detailCache = useRef(new Map<string, TradeSession>())
    const detailRequests = useRef(new Map<string, Promise<TradeSession>>())
    const deepLinked = useRef<string | null>(null)

    const loadSessions = useCallback(async (force = false) => {
        if (!force && listFetchedAt.current && Date.now() - listFetchedAt.current < LIST_TTL_MS) return
        if (listRequest.current) return listRequest.current

        const request = (async () => {
            try {
                setListLoading(true)
                setListError(null)
                const response = await fetch('/api/ai-trading/sessions', { method: 'GET' })
                if (!response.ok) throw new Error(`Trade history request failed (${response.status})`)
                const payload = await response.json()
                setSessions(Array.isArray(payload.sessions) ? payload.sessions : [])
                listFetchedAt.current = Date.now()
            } catch (error) {
                console.error('Error loading trade sessions:', error)
                setListError('Trade history is temporarily unavailable.')
            } finally {
                setListLoading(false)
                listRequest.current = null
            }
        })()
        listRequest.current = request
        return request
    }, [])

    useEffect(() => {
        void loadSessions()
    }, [loadSessions])

    const loadDetail = useCallback((sessionId: string) => {
        const cached = detailCache.current.get(sessionId)
        if (cached) return Promise.resolve(cached)

        const pending = detailRequests.current.get(sessionId)
        if (pending) return pending

        const request = (async () => {
            const response = await fetch(`/api/ai-trading/sessions/${encodeURIComponent(sessionId)}`, { method: 'GET' })
            if (!response.ok) throw new Error(`Trade session request failed (${response.status})`)
            const session: TradeSession = await response.json()
            detailCache.current.set(sessionId, session)
            return session
        })().finally(() => detailRequests.current.delete(sessionId))

        detailRequests.current.set(sessionId, request)
        return request
    }, [])

    /** Warm the cache on hover/focus so opening feels instant. */
    const prefetchSession = useCallback(
        (sessionId: string) => {
            void loadDetail(sessionId).catch(() => undefined)
        },
        [loadDetail],
    )

    const openSession = useCallback(
        async (sessionId: string) => {
            setOpeningId(sessionId)
            setDetailError(null)
            try {
                setSelected(await loadDetail(sessionId))
                deepLinked.current = sessionId
                window.scrollTo({ top: 0, behavior: 'smooth' })
            } catch (error) {
                console.error('Error opening trade session:', error)
                setDetailError('That run could not be opened. It may still be syncing — try again shortly.')
            } finally {
                setOpeningId(null)
            }
        },
        [loadDetail],
    )

    const closeSession = useCallback(() => {
        setSelected(null)
        setDetailError(null)
        deepLinked.current = null
    }, [])

    // Honour ?session=<id> on first load, without re-opening on every render.
    useEffect(() => {
        if (!initialSessionId || deepLinked.current === initialSessionId) return
        deepLinked.current = initialSessionId
        void openSession(initialSessionId)
    }, [initialSessionId, openSession])

    return {
        sessions,
        listLoading,
        listError,
        selected,
        openingId,
        detailError,
        reload: () => loadSessions(true),
        openSession,
        prefetchSession,
        closeSession,
    }
}
