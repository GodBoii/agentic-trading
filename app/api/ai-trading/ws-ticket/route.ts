import { randomUUID } from 'crypto'
import { NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

const backendUrl = process.env.AI_TRADING_BACKEND_URL?.replace(/\/$/, '')
const backendTimeoutMs = Number(process.env.AI_TRADING_BACKEND_TIMEOUT_MS || 10_000)

export async function POST() {
  const supabase = await createClient()
  const { data: { user }, error } = await supabase.auth.getUser()
  if (error || !user) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }
  const { data: { session } } = await supabase.auth.getSession()
  if (!session?.access_token) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }
  if (!backendUrl) {
    return NextResponse.json({ error: 'Trading stream is not configured' }, { status: 503 })
  }

  try {
    const response = await fetch(`${backendUrl}/ai-trading/ws-ticket`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${session.access_token}`,
        'Content-Type': 'application/json',
        'X-Request-ID': randomUUID(),
      },
      cache: 'no-store',
      signal: AbortSignal.timeout(backendTimeoutMs),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok) {
      console.warn('[WebSocket ticket] Backend rejected ticket request:', response.status)
      return NextResponse.json(
        { error: payload?.error || 'Trading stream authorization failed' },
        { status: response.status },
      )
    }
    return NextResponse.json(payload, {
      headers: {
        'Cache-Control': 'no-store, private',
      },
    })
  } catch (requestError) {
    console.warn('[WebSocket ticket] Backend unavailable:', requestError)
    return NextResponse.json({ error: 'Trading stream is unavailable' }, { status: 502 })
  }
}
