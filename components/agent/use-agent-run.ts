'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { isWireEvent, reduceLiveRuns, type LiveRun } from '@/lib/live-agent-runs'
import { websocketUrl } from '@/components/ai-trading/utils'
import type { AgentRunStatus, StreamState } from '@/components/ai-trading/types'

const POLL_INTERVAL_MS = 8_000
const RECONNECT_DELAY_MS = 2_500

/**
 * Owns the live agent run: status polling plus the event WebSocket.
 *
 * Extracted from the page so the view is declarative. Behaviour preserved from
 * the original implementation, including in-flight request de-duplication,
 * polling only while the tab is visible, sequence-based event de-duplication,
 * and reconnect-on-close.
 *
 * @param active When false, polling and the socket are torn down and the
 *               stream reports `paused` — used while the operator is on a
 *               different view.
 */
export function useAgentRun(active: boolean) {
    const [status, setStatus] = useState<AgentRunStatus | null>(null)
    const [runs, setRuns] = useState<Record<string, LiveRun>>({})
    const [stream, setStream] = useState<StreamState>('connecting')
    const [error, setError] = useState<string | null>(null)

    const inFlight = useRef<Promise<void> | null>(null)
    const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

    // Preserve the saved-result fallback when the event transport is unavailable.
    useEffect(() => {
        const requestId = status?.request?.request_id
        const results: unknown = status?.stages?.stock_agent?.details?.results
        if (!requestId || !Array.isArray(results)) return
        setRuns((current) => results.reduce<Record<string, LiveRun>>((next, result: unknown) => {
            if (!result || typeof result !== 'object') return next
            const completed: unknown = { ...result, type: 'stock_agent_completed', request_id: requestId,
                sent_at_utc: status?.stages?.stock_agent?.generated_at_utc || status?.updated_at_utc }
            if (!isWireEvent(completed) || !completed.rank) return next
            if (next[requestId]?.events[completed.rank]?.some((item) => item.type === 'stock_agent_completed')) return next
            let restored = next
            const timeline: unknown = completed.agent_metadata?.timeline
            if (Array.isArray(timeline)) {
                for (const entry of timeline) {
                    if (!entry || typeof entry !== 'object') continue
                    const replay: unknown = { ...entry, request_id: requestId, rank: completed.rank,
                        sent_at_utc: entry.sent_at_utc || (typeof entry.created_at === 'number' && Number.isFinite(entry.created_at)
                            ? new Date(entry.created_at * 1000).toISOString() : completed.sent_at_utc) }
                    if (isWireEvent(replay)) restored = reduceLiveRuns(restored, replay)
                }
            }
            return reduceLiveRuns(restored, completed)
        }, current))
    }, [status])

    const refresh = useCallback(() => {
        if (inFlight.current) return inFlight.current
        const request = (async () => {
            try {
                const response = await fetch('/api/ai-trading/toggle', { method: 'GET' })
                if (!response.ok) throw new Error(`Status request failed (${response.status})`)
                setStatus(await response.json())
                setError(null)
            } catch (statusError) {
                console.error('Error loading AI trading status:', statusError)
                setError('Could not load the latest agent run.')
            } finally {
                inFlight.current = null
            }
        })()
        inFlight.current = request
        return request
    }, [])

    // Poll status, but only while the tab is actually being looked at.
    useEffect(() => {
        if (!active) return
        void refresh()
        const timer = window.setInterval(() => {
            if (document.visibilityState === 'visible') void refresh()
        }, POLL_INTERVAL_MS)
        return () => window.clearInterval(timer)
    }, [active, refresh])

    useEffect(() => {
        if (!active) {
            setStream('paused')
            return
        }

        let socket: WebSocket | null = null
        let closedByCleanup = false

        const reconnect = () => {
            if (closedByCleanup) return
            setStream('reconnecting')
            reconnectTimer.current = setTimeout(() => void connect(), RECONNECT_DELAY_MS)
        }

        const connect = async () => {
            const baseUrl = websocketUrl()
            if (!baseUrl) {
                setStream('unavailable')
                return
            }
            try {
                setStream('connecting')
                const ticketResponse = await fetch('/api/ai-trading/ws-ticket', {
                    method: 'POST',
                    cache: 'no-store',
                })
                if (!ticketResponse.ok) {
                    throw new Error(`WebSocket ticket request failed (${ticketResponse.status})`)
                }
                const { ticket } = await ticketResponse.json()
                if (!ticket || closedByCleanup) return
                const url = new URL(baseUrl)
                url.searchParams.set('ticket', String(ticket))
                socket = new WebSocket(url.toString())
            } catch (socketError) {
                console.error('AI trading stream setup failed:', socketError)
                setStream('fallback')
                reconnect()
                return
            }

            socket.onopen = () => setStream('live')
            socket.onerror = () => setStream('fallback')
            socket.onclose = () => {
                reconnect()
            }

            socket.onmessage = (message) => {
                try {
                    const payload = JSON.parse(message.data)
                    if (payload.type === 'heartbeat') return

                    if ((payload.type === 'status_snapshot' || payload.type === 'status_update') && payload.status) {
                        setStatus(payload.status)
                        return
                    }

                    if (isWireEvent(payload)) setRuns((current) => reduceLiveRuns(current, payload))
                } catch (streamError) {
                    console.error('AI trading stream payload error:', streamError)
                }
            }
        }

        void connect()
        return () => {
            closedByCleanup = true
            if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
            socket?.close()
        }
    }, [active])

    const events = runs[status?.request?.request_id || 'legacy']?.events || {}
    return { status, runs, events, stream, error, refresh }
}
