import { v } from 'convex/values'
import { internalMutation, internalQuery } from './_generated/server'

const replaceChunks = async (
  ctx: any,
  ownerKey: string,
  payloadHash: string,
  chunks: string[],
) => {
  const oldChunks = await ctx.db
    .query('agentPayloadChunks')
    .withIndex('by_owner_and_index', (q: any) => q.eq('ownerKey', ownerKey))
    .collect()
  await Promise.all(oldChunks.map((chunk: any) => ctx.db.delete(chunk._id)))
  for (let index = 0; index < chunks.length; index += 1) {
    await ctx.db.insert('agentPayloadChunks', {
      ownerKey,
      chunkIndex: index,
      payloadHash,
      data: chunks[index],
    })
  }
}

export const replaceSession = internalMutation({
  args: {
    sessionId: v.string(),
    sessionType: v.string(),
    userId: v.optional(v.string()),
    componentId: v.optional(v.string()),
    runCount: v.number(),
    lastRunId: v.optional(v.string()),
    createdAt: v.optional(v.number()),
    updatedAt: v.number(),
    payloadHash: v.string(),
    payloadChunks: v.array(v.string()),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query('agentSessions')
      .withIndex('by_session_id', (q) => q.eq('sessionId', args.sessionId))
      .unique()
    const { payloadChunks, ...metadata } = args
    const record = { ...metadata, payloadChunkCount: payloadChunks.length }
    if (existing) await ctx.db.patch(existing._id, record)
    else await ctx.db.insert('agentSessions', record)
    await replaceChunks(ctx, `session:${args.sessionId}`, args.payloadHash, payloadChunks)
    return { sessionId: args.sessionId, payloadChunkCount: payloadChunks.length }
  },
})

export const replaceRun = internalMutation({
  args: {
    sessionId: v.string(),
    runId: v.string(),
    userId: v.optional(v.string()),
    runIndex: v.number(),
    status: v.optional(v.string()),
    contentPreview: v.optional(v.string()),
    createdAt: v.optional(v.number()),
    updatedAt: v.number(),
    payloadHash: v.string(),
    payloadChunks: v.array(v.string()),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query('agentRuns')
      .withIndex('by_run_id', (q) => q.eq('runId', args.runId))
      .unique()
    const { payloadChunks, ...metadata } = args
    const record = { ...metadata, payloadChunkCount: payloadChunks.length }
    if (existing) await ctx.db.patch(existing._id, record)
    else await ctx.db.insert('agentRuns', record)
    await replaceChunks(ctx, `run:${args.runId}`, args.payloadHash, payloadChunks)
    return { runId: args.runId, payloadChunkCount: payloadChunks.length }
  },
})

export const deleteSession = internalMutation({
  args: { sessionId: v.string(), userId: v.optional(v.string()) },
  handler: async (ctx, args) => {
    const session = await ctx.db
      .query('agentSessions')
      .withIndex('by_session_id', (q) => q.eq('sessionId', args.sessionId))
      .unique()
    if (!session || (args.userId !== undefined && session.userId !== args.userId)) return false

    const runs = await ctx.db
      .query('agentRuns')
      .withIndex('by_session_and_index', (q) => q.eq('sessionId', args.sessionId))
      .collect()
    for (const run of runs) {
      const chunks = await ctx.db
        .query('agentPayloadChunks')
        .withIndex('by_owner_and_index', (q) => q.eq('ownerKey', `run:${run.runId}`))
        .collect()
      await Promise.all(chunks.map((chunk) => ctx.db.delete(chunk._id)))
      await ctx.db.delete(run._id)
    }
    const chunks = await ctx.db
      .query('agentPayloadChunks')
      .withIndex('by_owner_and_index', (q) => q.eq('ownerKey', `session:${args.sessionId}`))
      .collect()
    await Promise.all(chunks.map((chunk) => ctx.db.delete(chunk._id)))
    await ctx.db.delete(session._id)
    return true
  },
})

export const listForUser = internalQuery({
  args: { userId: v.string(), limit: v.optional(v.number()) },
  handler: async (ctx, args) => {
    return await ctx.db
      .query('agentSessions')
      .withIndex('by_user_updated_at', (q) => q.eq('userId', args.userId))
      .order('desc')
      .take(Math.max(1, Math.min(args.limit ?? 50, 200)))
  },
})
