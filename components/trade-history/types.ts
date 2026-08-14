export interface TradeSessionSummary {
    session_id: string
    request_id: string
    title: string
    status: string
    created_at_utc?: string | null
    updated_at_utc?: string | null
    agent_count?: number
    executed_count?: number
    cloud_synced_at_utc?: string | null
    loaded_from_cloud?: boolean
}

export interface TradeDateGroup {
    key: string
    sessions: TradeSessionSummary[]
}
