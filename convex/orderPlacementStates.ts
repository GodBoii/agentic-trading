import { v } from 'convex/values'
import { internalMutation, internalQuery } from './_generated/server'

export const get = internalQuery({
  args: { broker: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query('orderPlacementStates')
      .withIndex('by_broker', (q) => q.eq('broker', args.broker))
      .unique()
  },
})

export const set = internalMutation({
  args: {
    broker: v.string(),
    allowed: v.boolean(),
    statusCode: v.string(),
    reason: v.string(),
    verifiedAt: v.string(),
    nextVerificationAt: v.string(),
    detectedIp: v.optional(v.string()),
    primaryIp: v.optional(v.string()),
    secondaryIp: v.optional(v.string()),
    ordersAllowed: v.optional(v.boolean()),
    brokerMessage: v.optional(v.string()),
    updatedAt: v.string(),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query('orderPlacementStates')
      .withIndex('by_broker', (q) => q.eq('broker', args.broker))
      .unique()
    if (existing) {
      await ctx.db.patch(existing._id, {
        ...args,
        detectedIp: args.detectedIp,
        primaryIp: args.primaryIp,
        secondaryIp: args.secondaryIp,
        ordersAllowed: args.ordersAllowed,
        brokerMessage: args.brokerMessage,
      })
      return await ctx.db.get(existing._id)
    }
    const id = await ctx.db.insert('orderPlacementStates', args)
    return await ctx.db.get(id)
  },
})
