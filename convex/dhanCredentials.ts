import { v } from 'convex/values'
import { internalMutation, internalQuery } from './_generated/server'

export const get = internalQuery({
  args: { supabaseUserId: v.string() },
  handler: async (ctx, args) =>
    await ctx.db
      .query('dhanCredentials')
      .withIndex('by_supabase_user_id', (q) => q.eq('supabaseUserId', args.supabaseUserId))
      .unique(),
})

export const upsertAuth = internalMutation({
  args: {
    supabaseUserId: v.string(),
    dhanClientId: v.string(),
    encryptedApiKey: v.string(),
    encryptedApiSecret: v.string(),
    updatedAt: v.string(),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query('dhanCredentials')
      .withIndex('by_supabase_user_id', (q) => q.eq('supabaseUserId', args.supabaseUserId))
      .unique()
    const values = {
      dhanClientId: args.dhanClientId,
      encryptedApiKey: args.encryptedApiKey,
      encryptedApiSecret: args.encryptedApiSecret,
      encryptedAccessToken: undefined,
      tokenExpiresAt: undefined,
      updatedAt: args.updatedAt,
    }
    if (existing) {
      await ctx.db.patch(existing._id, values)
      return existing._id
    }
    return await ctx.db.insert('dhanCredentials', {
      supabaseUserId: args.supabaseUserId,
      ...values,
      createdAt: args.updatedAt,
    })
  },
})

export const setToken = internalMutation({
  args: {
    supabaseUserId: v.string(),
    encryptedAccessToken: v.string(),
    tokenExpiresAt: v.string(),
    updatedAt: v.string(),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query('dhanCredentials')
      .withIndex('by_supabase_user_id', (q) => q.eq('supabaseUserId', args.supabaseUserId))
      .unique()
    if (!existing) throw new Error('Dhan API credentials are not configured')
    await ctx.db.patch(existing._id, {
      encryptedAccessToken: args.encryptedAccessToken,
      tokenExpiresAt: args.tokenExpiresAt,
      updatedAt: args.updatedAt,
    })
  },
})

export const remove = internalMutation({
  args: { supabaseUserId: v.string() },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query('dhanCredentials')
      .withIndex('by_supabase_user_id', (q) => q.eq('supabaseUserId', args.supabaseUserId))
      .unique()
    if (!existing) return false
    await ctx.db.delete(existing._id)
    return true
  },
})
