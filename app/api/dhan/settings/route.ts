import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import { convexAdminMutation } from '@/lib/convex/server'
import { getStoredDhanCredentials } from '@/lib/dhan/user-credentials'
import { encryptDhanCredential } from '@/lib/dhan/credential-crypto'

export const runtime = 'nodejs'

function text(value: unknown): string { return typeof value === 'string' ? value.trim() : '' }

function profileExpiry(value: unknown): string | null {
  const match = text(value).match(/^(\d{2})\/(\d{2})\/(\d{4}) (\d{2}):(\d{2})$/)
  if (!match) return null
  const date = new Date(`${match[3]}-${match[2]}-${match[1]}T${match[4]}:${match[5]}:00+05:30`)
  return Number.isFinite(date.getTime()) && date.getTime() > Date.now() ? date.toISOString() : null
}

export async function PUT(request: NextRequest) {
  const { data: { user }, error } = await (await createClient()).auth.getUser()
  if (error || !user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  if (request.headers.get('origin') && request.headers.get('origin') !== request.nextUrl.origin) {
    return NextResponse.json({ error: 'Invalid request origin' }, { status: 403 })
  }
  const input: unknown = await request.json().catch(() => null)
  if (!input || typeof input !== 'object' || Array.isArray(input)) return NextResponse.json({ error: 'Invalid settings' }, { status: 400 })
  const field = (key: string) => text(Reflect.get(input, key))
  const clientId = field('dhanClientId'), apiKey = field('apiKey'), apiSecret = field('apiSecret')
  const accessToken = field('accessToken'), pin = field('pin'), totpSecret = field('totpSecret').replace(/\s/g, '').toUpperCase()
  const autoRenew = Reflect.get(input, 'autoRenew') === true
  const clearRecovery = Reflect.get(input, 'clearRecovery') === true
  const invalid = !/^\d{5,20}$/.test(clientId) || [apiKey, apiSecret, accessToken].some(v => v.length > 8192)
    || (pin !== '' && !/^\d{6}$/.test(pin)) || (totpSecret !== '' && !/^[A-Z2-7]{16,128}$/.test(totpSecret))
    || Boolean(pin) !== Boolean(totpSecret) || (clearRecovery && Boolean(pin))
  if (invalid) return NextResponse.json({ error: 'Check Client ID, the six-digit PIN and the TOTP setup secret. Enter both recovery fields together.' }, { status: 400 })
  try {
    const existing = await getStoredDhanCredentials(user.id)
    if (existing && existing.dhanClientId !== clientId) return NextResponse.json({ error: 'Disconnect the current account before changing Client ID.' }, { status: 409 })
    if ((!existing && (!apiKey || !apiSecret || !accessToken)) || Boolean(apiKey) !== Boolean(apiSecret)) {
      return NextResponse.json({ error: 'For first setup, provide API key, API secret and a current Dhan Web access token.' }, { status: 400 })
    }
    if (autoRenew && !pin && !(existing?.encryptedPin && existing.encryptedTotpSecret && !clearRecovery) && existing?.tokenSource !== 'scanner') {
      return NextResponse.json({ error: 'Add PIN and TOTP setup secret to enable automatic recovery.' }, { status: 400 })
    }
    let expiresAt: string | null = null
    if (accessToken) {
      const response = await fetch('https://api.dhan.co/v2/profile', { headers: { 'access-token': accessToken }, cache: 'no-store', signal: AbortSignal.timeout(8000) })
      const profile: unknown = await response.json().catch(() => null)
      if (!response.ok || !profile || typeof profile !== 'object' || text(Reflect.get(profile, 'dhanClientId')) !== clientId) {
        return NextResponse.json({ error: 'Dhan rejected the token or it belongs to a different account.' }, { status: 400 })
      }
      expiresAt = profileExpiry(Reflect.get(profile, 'tokenValidity'))
      if (!expiresAt) return NextResponse.json({ error: 'Dhan did not confirm a valid token expiry.' }, { status: 400 })
    }
    const encryptedApiKey = apiKey ? encryptDhanCredential(apiKey, user.id, 'api-key') : existing?.encryptedApiKey
    const encryptedApiSecret = apiSecret ? encryptDhanCredential(apiSecret, user.id, 'api-secret') : existing?.encryptedApiSecret
    if (!encryptedApiKey || !encryptedApiSecret) return NextResponse.json({ error: 'API credentials are required.' }, { status: 400 })
    await convexAdminMutation('dhanCredentials:saveSettings', {
      supabaseUserId: user.id, dhanClientId: clientId, encryptedApiKey, encryptedApiSecret, autoRenew, clearRecovery,
      ...(existing ? { expectedUpdatedAt: existing.updatedAt } : {}),
      ...(accessToken ? { encryptedAccessToken: encryptDhanCredential(accessToken, user.id, 'access-token'), tokenExpiresAt: expiresAt } : {}),
      ...(pin ? { encryptedPin: encryptDhanCredential(pin, user.id, 'pin'), encryptedTotpSecret: encryptDhanCredential(totpSecret, user.id, 'totp-secret') } : {}),
    })
    return NextResponse.json({ success: true })
  } catch {
    return NextResponse.json({ error: 'Settings could not be saved. Refresh and retry; authentication may be updating.' }, { status: 503 })
  }
}
