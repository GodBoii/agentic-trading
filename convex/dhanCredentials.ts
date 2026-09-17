import { v } from 'convex/values'
import { internalMutation, internalQuery } from './_generated/server'

function nextRevision(previous?: string) {
  const old = Date.parse(previous || '')
  return new Date(Math.max(Date.now(), Number.isFinite(old) ? old + 1 : 0)).toISOString()
}

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
    if (existing && existing.dhanClientId !== args.dhanClientId) {
      throw new Error('Disconnect the current Dhan account before changing Client ID')
    }
    const duplicate = (await ctx.db.query('dhanCredentials').collect()).some(
      r => r.dhanClientId === args.dhanClientId && r.supabaseUserId !== args.supabaseUserId,
    )
    if (duplicate) throw new Error('This Dhan account is already connected')
    if (existing?.leaseUntil && existing.leaseUntil > Date.now()) throw new Error('Authentication update in progress')
    const values = {
      dhanClientId: args.dhanClientId,
      encryptedApiKey: args.encryptedApiKey,
      encryptedApiSecret: args.encryptedApiSecret,
      updatedAt: nextRevision(existing?.updatedAt),
    }
    if (existing) {
      await ctx.db.patch(existing._id, {
        ...values,
        ...(existing.dhanClientId === args.dhanClientId
          ? {}
          : { encryptedAccessToken: undefined, tokenExpiresAt: undefined }),
      })
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
    expectedUpdatedAt: v.string(),
    dhanClientId: v.string(),
    owner: v.string(),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query('dhanCredentials')
      .withIndex('by_supabase_user_id', (q) => q.eq('supabaseUserId', args.supabaseUserId))
      .unique()
    if (!existing) throw new Error('Dhan API credentials are not configured')
    if (existing.updatedAt !== args.expectedUpdatedAt || existing.dhanClientId !== args.dhanClientId
      || existing.leaseOwner !== args.owner || (existing.leaseUntil ?? 0) <= Date.now()) throw new Error('Credentials changed; retry authentication')
    await ctx.db.patch(existing._id, {
      encryptedAccessToken: args.encryptedAccessToken,
      tokenExpiresAt: args.tokenExpiresAt,
      updatedAt: nextRevision(existing.updatedAt),
      tokenIssuedAt: args.updatedAt,
      accountVerifiedAt: args.updatedAt,
      tokenSource: 'consent',
      authStatus: 'pending',
      authError: undefined,
      leaseOwner: undefined,
      leaseUntil: undefined,
    })
  },
})

// Only trusted backend clients can read ciphertext or manage renewal leases.
export const listAll = internalQuery({ args: {}, handler: async (ctx) => await ctx.db.query('dhanCredentials').collect() })

export const saveSettings = internalMutation({
  args: {
    supabaseUserId: v.string(), dhanClientId: v.string(), expectedUpdatedAt: v.optional(v.string()),
    encryptedApiKey: v.string(), encryptedApiSecret: v.string(),
    encryptedAccessToken: v.optional(v.string()), tokenExpiresAt: v.optional(v.string()),
    encryptedPin: v.optional(v.string()), encryptedTotpSecret: v.optional(v.string()),
    autoRenew: v.boolean(), clearRecovery: v.boolean(),
  },
  handler: async (ctx, args) => {
    const all = await ctx.db.query('dhanCredentials').collect()
    const existing = all.find((r) => r.supabaseUserId === args.supabaseUserId)
    if (all.some((r) => r.dhanClientId === args.dhanClientId && r.supabaseUserId !== args.supabaseUserId)) {
      throw new Error('This Dhan account is already connected')
    }
    if (existing && (existing.updatedAt !== args.expectedUpdatedAt || existing.dhanClientId !== args.dhanClientId
      || (existing.leaseUntil ?? 0) > Date.now())) throw new Error('Credentials changed; reload and retry')
    if (!existing && args.expectedUpdatedAt) throw new Error('Account was disconnected')
    const now = nextRevision(existing?.updatedAt)
    const values = {
      dhanClientId: args.dhanClientId, encryptedApiKey: args.encryptedApiKey, encryptedApiSecret: args.encryptedApiSecret,
      autoRenew: args.autoRenew, updatedAt: now, authStatus: 'pending', authError: undefined,
      ...(args.clearRecovery ? { encryptedPin: undefined, encryptedTotpSecret: undefined } : {
        ...(args.encryptedPin ? { encryptedPin: args.encryptedPin } : {}),
        ...(args.encryptedTotpSecret ? { encryptedTotpSecret: args.encryptedTotpSecret } : {}),
      }),
      ...(args.encryptedAccessToken ? {
        encryptedAccessToken: args.encryptedAccessToken, tokenExpiresAt: args.tokenExpiresAt,
        tokenIssuedAt: now, accountVerifiedAt: now, tokenSource: 'web',
      } : {}),
    }
    if (existing) await ctx.db.patch(existing._id, values)
    else await ctx.db.insert('dhanCredentials', { ...values, supabaseUserId: args.supabaseUserId, createdAt: now })
  },
})

export const acquireLease = internalMutation({
  args: { supabaseUserId: v.string(), expectedUpdatedAt: v.string(), owner: v.string() },
  handler: async (ctx, args) => {
    const row = await ctx.db.query('dhanCredentials').withIndex('by_supabase_user_id', q => q.eq('supabaseUserId', args.supabaseUserId)).unique()
    if (!row || row.updatedAt !== args.expectedUpdatedAt
      || ((row.leaseUntil ?? 0) > Date.now() && row.leaseOwner !== args.owner)) return false
    await ctx.db.patch(row._id, { leaseOwner: args.owner, leaseUntil: Date.now() + 180_000 })
    return true
  },
})

export const finishCheck = internalMutation({
  args: {
    supabaseUserId: v.string(), expectedUpdatedAt: v.string(), owner: v.string(),
    authStatus: v.string(), authError: v.optional(v.string()),
    encryptedAccessToken: v.optional(v.string()), tokenExpiresAt: v.optional(v.string()),
    tokenIssuedAt: v.optional(v.string()), tokenSource: v.optional(v.string()),
    nextRenewalAt: v.optional(v.string()), accountVerifiedAt: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const row = await ctx.db.query('dhanCredentials').withIndex('by_supabase_user_id', q => q.eq('supabaseUserId', args.supabaseUserId)).unique()
    if (!row || row.updatedAt !== args.expectedUpdatedAt || row.leaseOwner !== args.owner || (row.leaseUntil ?? 0) <= Date.now()) return false
    const { supabaseUserId, expectedUpdatedAt, owner, ...values } = args
    const now = nextRevision(row.updatedAt)
    await ctx.db.patch(row._id, {
      ...values, authError: args.authError, lastCheckedAt: now, leaseOwner: undefined, leaseUntil: undefined,
      nextRenewalAt: args.nextRenewalAt,
      ...(args.encryptedAccessToken ? { updatedAt: now, lastRenewedAt: now } : {}),
    })
    return true
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
