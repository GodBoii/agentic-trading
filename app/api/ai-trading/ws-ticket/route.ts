import crypto from 'crypto'
import { NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

const audience = 'ai-trading-websocket'
const issuer = 'polycognition-web'

function encodeJson(value: Record<string, unknown>) {
  return Buffer.from(JSON.stringify(value), 'utf8').toString('base64url')
}

export async function POST() {
  const supabase = await createClient()
  const { data: { user }, error } = await supabase.auth.getUser()
  if (error || !user) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const signingSecret =
    process.env.AI_TRADING_WS_SIGNING_SECRET?.trim() ||
    process.env.AI_TRADING_BACKEND_TOKEN?.trim()
  if (!signingSecret || signingSecret.length < 32 || signingSecret.startsWith('replace_with_')) {
    console.error(
      'The WebSocket signing key must contain at least 32 characters. Set a strong AI_TRADING_BACKEND_TOKEN or override it with AI_TRADING_WS_SIGNING_SECRET.',
    )
    return NextResponse.json({ error: 'Trading stream is not configured' }, { status: 503 })
  }

  const configuredTtl = Number(process.env.AI_TRADING_WS_TICKET_TTL_SECONDS || 45)
  const ttlSeconds = Number.isFinite(configuredTtl)
    ? Math.min(120, Math.max(15, Math.round(configuredTtl)))
    : 45
  const issuedAt = Math.floor(Date.now() / 1000)
  const expiresAt = issuedAt + ttlSeconds
  const header = encodeJson({ alg: 'HS256', typ: 'JWT' })
  const payload = encodeJson({
    iss: issuer,
    aud: audience,
    sub: user.id,
    iat: issuedAt,
    exp: expiresAt,
    jti: crypto.randomUUID(),
  })
  const signingInput = `${header}.${payload}`
  const signature = crypto
    .createHmac('sha256', signingSecret)
    .update(signingInput)
    .digest('base64url')

  return NextResponse.json(
    {
      ticket: `${signingInput}.${signature}`,
      expires_at: new Date(expiresAt * 1000).toISOString(),
    },
    {
      headers: {
        'Cache-Control': 'no-store, private',
      },
    },
  )
}
