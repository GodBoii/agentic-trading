import { defineSchema, defineTable } from 'convex/server'
import { v } from 'convex/values'

export default defineSchema({
  tradingConfigurations: defineTable({
    supabaseUserId: v.string(),
    enabled: v.boolean(),
    tradeMode: v.union(v.literal('auto'), v.literal('manual')),
    tradeAmount: v.optional(v.number()),
    amountUpdatedAt: v.optional(v.string()),
    statusCode: v.optional(v.string()),
    createdAt: v.string(),
    updatedAt: v.string(),
  }).index('by_supabase_user_id', ['supabaseUserId']),

  agentSessions: defineTable({
    sessionId: v.string(),
    sessionType: v.string(),
    userId: v.optional(v.string()),
    componentId: v.optional(v.string()),
    runCount: v.number(),
    lastRunId: v.optional(v.string()),
    createdAt: v.optional(v.number()),
    updatedAt: v.number(),
    payloadHash: v.string(),
    payloadChunkCount: v.number(),
  })
    .index('by_session_id', ['sessionId'])
    .index('by_user_updated_at', ['userId', 'updatedAt']),

  agentRuns: defineTable({
    sessionId: v.string(),
    runId: v.string(),
    userId: v.optional(v.string()),
    runIndex: v.number(),
    status: v.optional(v.string()),
    contentPreview: v.optional(v.string()),
    createdAt: v.optional(v.number()),
    updatedAt: v.number(),
    payloadHash: v.string(),
    payloadChunkCount: v.number(),
  })
    .index('by_run_id', ['runId'])
    .index('by_session_and_index', ['sessionId', 'runIndex'])
    .index('by_user_updated_at', ['userId', 'updatedAt']),

  agentPayloadChunks: defineTable({
    ownerKey: v.string(),
    chunkIndex: v.number(),
    payloadHash: v.string(),
    data: v.string(),
  }).index('by_owner_and_index', ['ownerKey', 'chunkIndex']),
})
