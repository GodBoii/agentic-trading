import 'server-only'
import { convexAdminMutation, convexAdminQuery } from '@/lib/convex/server'
import { decryptDhanCredential, encryptDhanCredential } from './credential-crypto'

export type StoredDhanCredentials = {
  supabaseUserId: string
  dhanClientId: string
  encryptedApiKey: string
  encryptedApiSecret: string
  encryptedAccessToken?: string
  tokenExpiresAt?: string
  updatedAt: string
}

export async function getStoredDhanCredentials(userId: string) {
  return await convexAdminQuery<StoredDhanCredentials | null>('dhanCredentials:get', {
    supabaseUserId: userId,
  })
}

export async function getDhanAuthCredentials(userId: string) {
  const stored = await getStoredDhanCredentials(userId)
  if (!stored) return null
  return {
    clientId: stored.dhanClientId,
    apiKey: decryptDhanCredential(stored.encryptedApiKey, userId, 'api-key'),
    apiSecret: decryptDhanCredential(stored.encryptedApiSecret, userId, 'api-secret'),
  }
}

export async function getDhanAccessCredentials(userId: string) {
  const stored = await getStoredDhanCredentials(userId)
  if (!stored?.encryptedAccessToken || !stored.tokenExpiresAt) return null
  return {
    clientId: stored.dhanClientId,
    accessToken: decryptDhanCredential(stored.encryptedAccessToken, userId, 'access-token'),
    expiresAt: stored.tokenExpiresAt,
  }
}

export async function saveDhanAuthCredentials(
  userId: string,
  values: { clientId: string; apiKey: string; apiSecret: string },
) {
  const now = new Date().toISOString()
  await convexAdminMutation('dhanCredentials:upsertAuth', {
    supabaseUserId: userId,
    dhanClientId: values.clientId,
    encryptedApiKey: encryptDhanCredential(values.apiKey, userId, 'api-key'),
    encryptedApiSecret: encryptDhanCredential(values.apiSecret, userId, 'api-secret'),
    updatedAt: now,
  })
}

export async function saveDhanAccessToken(
  userId: string,
  values: { accessToken: string; expiresAt: string },
) {
  await convexAdminMutation('dhanCredentials:setToken', {
    supabaseUserId: userId,
    encryptedAccessToken: encryptDhanCredential(values.accessToken, userId, 'access-token'),
    tokenExpiresAt: values.expiresAt,
    updatedAt: new Date().toISOString(),
  })
}

export async function removeDhanCredentials(userId: string) {
  return await convexAdminMutation<boolean>('dhanCredentials:remove', { supabaseUserId: userId })
}
