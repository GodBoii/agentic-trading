import { v } from 'convex/values'
import { internalMutation, internalQuery } from './_generated/server'

export const get = internalQuery({
  args: { supabaseUserId: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query('tradingConfigurations')
      .withIndex('by_supabase_user_id', (q) => q.eq('supabaseUserId', args.supabaseUserId))
      .unique()
  },
})

export const listAll = internalQuery({
  args: {},
  handler: async (ctx) => await ctx.db.query('tradingConfigurations').collect(),
})

export const upsert = internalMutation({
  args: {
    supabaseUserId: v.string(),
    enabled: v.optional(v.boolean()),
    tradeMode: v.optional(v.union(v.literal('auto'), v.literal('manual'))),
    tradeAmount: v.optional(v.number()),
    clearTradeAmount: v.optional(v.boolean()),
    amountUpdatedAt: v.optional(v.string()),
    statusCode: v.optional(v.string()),
    updatedAt: v.string(),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query('tradingConfigurations')
      .withIndex('by_supabase_user_id', (q) => q.eq('supabaseUserId', args.supabaseUserId))
      .unique()

    const update = {
      ...(args.enabled === undefined ? {} : { enabled: args.enabled }),
      ...(args.tradeMode === undefined ? {} : { tradeMode: args.tradeMode }),
      ...(args.tradeAmount === undefined ? {} : { tradeAmount: args.tradeAmount }),
      ...(args.clearTradeAmount ? { tradeAmount: undefined } : {}),
      ...(args.amountUpdatedAt === undefined ? {} : { amountUpdatedAt: args.amountUpdatedAt }),
      ...(args.statusCode === undefined ? {} : { statusCode: args.statusCode }),
      updatedAt: args.updatedAt,
    }

    if (existing) {
      await ctx.db.patch(existing._id, update)
      return await ctx.db.get(existing._id)
    }

    const id = await ctx.db.insert('tradingConfigurations', {
      supabaseUserId: args.supabaseUserId,
      enabled: args.enabled ?? false,
      tradeMode: args.tradeMode ?? 'auto',
      ...(args.tradeAmount === undefined ? {} : { tradeAmount: args.tradeAmount }),
      ...(args.amountUpdatedAt === undefined ? {} : { amountUpdatedAt: args.amountUpdatedAt }),
      ...(args.statusCode === undefined ? {} : { statusCode: args.statusCode }),
      createdAt: args.updatedAt,
      updatedAt: args.updatedAt,
    })
    return await ctx.db.get(id)
  },
})

export const remove = internalMutation({
  args: { supabaseUserId: v.string() },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query('tradingConfigurations')
      .withIndex('by_supabase_user_id', (q) => q.eq('supabaseUserId', args.supabaseUserId))
      .unique()
    if (!existing) return false
    await ctx.db.delete(existing._id)
    return true
  },
})
