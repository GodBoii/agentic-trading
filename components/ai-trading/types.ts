export interface AgentStage {
    status: string
    generated_at_utc?: string | null
    summary?: Record<string, any> | null
    details?: Record<string, any> | null
}

export interface AgentRunStatus {
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

export interface AgentAttachments {
    images?: AgentImageCard[]
    files?: AgentFileCard[]
}

export interface AgentImageCard {
    id?: string
    title?: string
    filename?: string
    path?: string
    url?: string
    cloud_url?: string | null
    storage_path?: string
    day_type?: string
    date?: string
    timeframe?: string
    candles?: number
}

export interface AgentFileCard {
    id?: string
    title?: string
    filename?: string
    content_type?: string
    content?: string
    path?: string
    url?: string
    cloud_url?: string | null
    storage_path?: string
}

export interface LiveAgentEvent {
    type: string
    sequence?: number
    rank?: number
    security_id?: number
    symbol?: string
    display_name?: string
    message?: string
    decision?: Record<string, any>
    attachments?: AgentAttachments
    agent_metadata?: Record<string, any>
    chart_count?: number
    report_text?: string
    error?: string
    sent_at_utc?: string
    created_at?: number
    input?: Record<string, any>
    tool_call_id?: string
    tool_name?: string
    tool_args?: Record<string, any>
    duration_seconds?: number
    result_length?: number
    result_preview?: string
    result?: string
    result_status?: string
    result_partial?: boolean
}

export interface AgentResult {
    rank?: number
    symbol?: string
    display_name?: string
    decision?: Record<string, any>
    attachments?: AgentAttachments
    agent_metadata?: Record<string, any> | null
    analysis?: string
    report_text?: string
}

export interface TradeSession {
    session_id: string
    request_id?: string
    title: string
    status: string
    created_at_utc?: string | null
    updated_at_utc?: string | null
    request?: Record<string, any>
    summary?: Record<string, any> | null
    status_snapshot?: AgentRunStatus
    agents?: AgentResult[]
    cloud_synced_at_utc?: string | null
    loaded_from_cloud?: boolean
}

/**
 * Live stream health. Previously a bare `string` compared with
 * `connectionState.includes('live')`, which silently matched nothing for
 * several of the states the socket actually sets.
 */
export type StreamState =
    | 'connecting'
    | 'live'
    | 'fallback'
    | 'reconnecting'
    | 'unavailable'
    | 'paused'
    | 'archive'
