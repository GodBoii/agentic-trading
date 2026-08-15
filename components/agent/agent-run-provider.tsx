'use client'

import { createContext, useContext, type ReactNode } from 'react'
import { useAgentRun } from '@/components/agent/use-agent-run'

type AgentRunContextValue = ReturnType<typeof useAgentRun>

const AgentRunContext = createContext<AgentRunContextValue | null>(null)

/**
 * Keeps one authenticated backend connection alive for the complete dashboard
 * session. The dashboard layout survives navigation between Portfolio, Agent,
 * and Trades, so the WebSocket is not repeatedly torn down and recreated.
 */
export function AgentRunProvider({ children }: { children: ReactNode }) {
    const run = useAgentRun(true)
    return <AgentRunContext.Provider value={run}>{children}</AgentRunContext.Provider>
}

export function useAgentRunContext() {
    const value = useContext(AgentRunContext)
    if (!value) {
        throw new Error('useAgentRunContext must be used inside AgentRunProvider')
    }
    return value
}
