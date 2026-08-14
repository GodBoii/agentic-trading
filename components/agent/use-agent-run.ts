'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { websocketUrl } from '@/components/ai-trading/utils'
import type { AgentRunStatus, LiveAgentEvent, StreamState } from '@/components/ai-trading/types'

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
    const [events, setEvents] = useState<Record<number, LiveAgentEvent[]>>({})
    const [stream, setStream] = useState<StreamState>('connecting')
    const [error, setError] = useState<string | null>(null)

    const inFlight = useRef<Promise<void> | null>(null)
    const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

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

        const connect = () => {
            const url = websocketUrl()
            if (!url) {
                setStream('unavailable')
                return
            }
            try {
                setStream('connecting')
                socket = new WebSocket(url)
            } catch (socketError) {
                console.error('AI trading stream setup failed:', socketError)
                setStream('fallback')
                return
            }

            socket.onopen = () => setStream('live')
            socket.onerror = () => setStream('fallback')
            socket.onclose = () => {
                if (closedByCleanup) return
                setStream('reconnecting')
                reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS)
            }

            socket.onmessage = (message) => {
                try {
                    const payload = JSON.parse(message.data)
                    if (payload.type === 'heartbeat') return

                    if ((payload.type === 'status_snapshot' || payload.type === 'status_update') && payload.status) {
                        setStatus(payload.status)
                        return
                    }

                    // A fresh selection replaces the board: new candidates mean
                    // the previous run's slots are no longer meaningful.
                    if (payload.type === 'stock_agent_selection') {
                        const next: Record<number, LiveAgentEvent[]> = {}
                        for (const selected of payload.selected || []) {
                            const rank = Number(selected.rank || 0)
                            if (!rank) continue
                            next[rank] = [
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
                        setEvents(next)
                        return
                    }

                    if (payload.type === 'stock_agent_no_trade') {
                        setEvents({
                            1: [
                                {
                                    type: 'stock_agent_no_trade',
                                    rank: 1,
                                    message: payload.reason || 'No stock qualified.',
                                    sent_at_utc: payload.sent_at_utc,
                                },
                            ],
                        })
                        return
                    }

                    if (typeof payload.rank === 'number') {
                        const rank = Number(payload.rank)
                        setEvents((current) => {
                            const existing = current[rank] || []
                            // The backend may resend on reconnect; (sequence, type) is the identity.
                            const duplicate =
                                payload.sequence !== undefined &&
                                existing.some(
                                    (item) => item.sequence === Number(payload.sequence) && item.type === payload.type,
                                )
                            if (duplicate) return current
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
        }

        connect()
        return () => {
            closedByCleanup = true
            if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
            socket?.close()
        }
    }, [active])

    return { status, events, stream, error, refresh }
}
