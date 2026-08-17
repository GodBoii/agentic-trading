import 'server-only'
import { ConvexHttpClient } from 'convex/browser'
import { makeFunctionReference } from 'convex/server'

type ConvexArgs = Record<string, unknown>

function createAdminClient() {
  const url = (process.env.CONVEX_URL || process.env.NEXT_PUBLIC_CONVEX_URL || '').trim()
  const adminKey = (process.env.CONVEX_ADMIN_KEY || '').trim()
  if (!url || !adminKey) {
    throw new Error('Convex is not configured. Set CONVEX_URL and CONVEX_ADMIN_KEY on the server.')
  }
  const client = new ConvexHttpClient(url)
  // Convex exposes this runtime method for trusted server clients, but marks it
  // internal in the public TypeScript declaration.
  ;(client as ConvexHttpClient & { setAdminAuth(token: string): void }).setAdminAuth(adminKey)
  return client
}

export function isConvexConfigured() {
  return Boolean(
    (process.env.CONVEX_URL || process.env.NEXT_PUBLIC_CONVEX_URL || '').trim()
      && (process.env.CONVEX_ADMIN_KEY || '').trim(),
  )
}

export async function convexAdminQuery<T>(name: string, args: ConvexArgs = {}) {
  const reference = makeFunctionReference<'query', ConvexArgs, T>(name)
  return await createAdminClient().query(reference, args)
}

export async function convexAdminMutation<T>(name: string, args: ConvexArgs = {}) {
  const reference = makeFunctionReference<'mutation', ConvexArgs, T>(name)
  return await createAdminClient().mutation(reference, args)
}
