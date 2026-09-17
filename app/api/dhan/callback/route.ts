import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import { getDhanAuthCredentials, saveDhanAccessToken } from '@/lib/dhan/user-credentials'
import { parseDhanExpiryIso } from '../_utils'
import { convexAdminMutation } from '@/lib/convex/server'
import { randomUUID } from 'crypto'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

function field(value: unknown, name: string) {
  if (typeof value !== 'object' || value === null || !(name in value)) return ''
  const candidate = Reflect.get(value, name)
  return typeof candidate === 'string' ? candidate.trim() : ''
}

export async function GET(request: NextRequest) {
  const tokenId = request.nextUrl.searchParams.get('tokenId')?.trim()
  if (!tokenId) return NextResponse.redirect(new URL('/dashboard?error=missing_token', request.url))

  const supabase = await createClient()
  const { data: { user }, error: authError } = await supabase.auth.getUser()
  if (authError || !user) {
    return NextResponse.redirect(new URL('/login?error=unauthorized_callback', request.url))
  }

  let lease: { supabaseUserId: string; expectedUpdatedAt: string; owner: string } | null = null
  try {
    const credentials = await getDhanAuthCredentials(user.id)
    if (!credentials) return NextResponse.redirect(new URL('/dashboard?error=credentials_missing', request.url))
    if (request.cookies.get('dhan-consent-revision')?.value !== credentials.updatedAt) {
      return NextResponse.redirect(new URL('/dashboard?error=credentials_changed', request.url))
    }
    lease = { supabaseUserId: user.id, expectedUpdatedAt: credentials.updatedAt, owner: randomUUID() }
    if (!await convexAdminMutation<boolean>('dhanCredentials:acquireLease', lease)) {
      return NextResponse.redirect(new URL('/dashboard?error=credentials_changed', request.url))
    }

    const response = await fetch(
      `https://auth.dhan.co/app/consumeApp-consent?tokenId=${encodeURIComponent(tokenId)}`,
      {
        headers: { app_id: credentials.apiKey, app_secret: credentials.apiSecret },
        cache: 'no-store',
        signal: AbortSignal.timeout(8_000),
      },
    )
    const payload: unknown = await response.json().catch(() => null)
    const accessToken = field(payload, 'accessToken')
    const clientId = field(payload, 'dhanClientId')
    const expiresAt = parseDhanExpiryIso(field(payload, 'expiryTime'))
    if (!response.ok || !accessToken || clientId !== credentials.clientId || !expiresAt) {
      return NextResponse.redirect(new URL('/dashboard?error=token_exchange_failed', request.url))
    }

    await saveDhanAccessToken(user.id, { accessToken, expiresAt, expectedUpdatedAt: credentials.updatedAt, clientId, owner: lease.owner })
    // Remove the old Supabase copy after a successful Convex migration.
    await supabase.from('user_trading_keys').delete().eq('user_id', user.id)
    const result = NextResponse.redirect(new URL('/dashboard?success=true', request.url))
    result.cookies.set('dhan-consent-revision', '', { maxAge: 0, path: '/api/dhan' })
    return result
  } catch (error) {
    console.error('Dhan callback failed')
    return NextResponse.redirect(new URL('/dashboard?error=unexpected', request.url))
  } finally {
    if (lease) {
      await convexAdminMutation('dhanCredentials:finishCheck', { ...lease, authStatus: 'pending' }).catch(() => {
        console.error('Dhan callback lease release pending')
      })
    }
  }
}
