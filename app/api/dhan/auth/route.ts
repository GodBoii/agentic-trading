import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import { getDhanAuthCredentials, saveDhanAuthCredentials } from '@/lib/dhan/user-credentials'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

function text(value: unknown) {
  return typeof value === 'string' ? value.trim() : ''
}

function inputObject(value: unknown) {
  if (typeof value !== 'object' || value === null) return null
  return value
}

export async function POST(request: NextRequest) {
  const supabase = await createClient()
  const { data: { user }, error: authError } = await supabase.auth.getUser()
  if (authError || !user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const input = inputObject(await request.json().catch(() => null))
  const supplied = {
    clientId: input && 'dhanClientId' in input ? text(input.dhanClientId) : '',
    apiKey: input && 'apiKey' in input ? text(input.apiKey) : '',
    apiSecret: input && 'apiSecret' in input ? text(input.apiSecret) : '',
  }
  const suppliedCount = Object.values(supplied).filter(Boolean).length
  if (suppliedCount !== 0 && suppliedCount !== 3) {
    return NextResponse.json({ error: 'Client ID, API key and API secret are all required.' }, { status: 400 })
  }

  try {
    const credentials = suppliedCount === 3 ? supplied : await getDhanAuthCredentials(user.id)
    if (!credentials) {
      return NextResponse.json({ error: 'Enter your Dhan Client ID, API key and API secret.' }, { status: 409 })
    }

    const response = await fetch(
      `https://auth.dhan.co/app/generate-consent?client_id=${encodeURIComponent(credentials.clientId)}`,
      {
        method: 'POST',
        headers: { app_id: credentials.apiKey, app_secret: credentials.apiSecret },
        cache: 'no-store',
        signal: AbortSignal.timeout(8_000),
      },
    )
    const payload: unknown = await response.json().catch(() => null)
    const consentAppId =
      payload && typeof payload === 'object' && 'consentAppId' in payload
        ? text(payload.consentAppId)
        : ''
    if (!response.ok || !consentAppId) {
      return NextResponse.json({ error: 'Dhan rejected these API credentials.' }, { status: 502 })
    }

    if (suppliedCount === 3) await saveDhanAuthCredentials(user.id, credentials)
    return NextResponse.json({
      url: `https://auth.dhan.co/login/consentApp-login?consentAppId=${encodeURIComponent(consentAppId)}`,
    })
  } catch (error) {
    console.error('Dhan consent initiation failed:', error)
    return NextResponse.json({ error: 'Unable to start Dhan authentication.' }, { status: 500 })
  }
}
