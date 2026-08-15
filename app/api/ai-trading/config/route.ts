import { NextRequest, NextResponse } from 'next/server'
import { promises as fs } from 'fs'
import path from 'path'
import { createClient } from '@/lib/supabase/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

const statePath = path.join(process.cwd(), 'python-backend', 'ai_trading_state.json')
const backendUrl = process.env.AI_TRADING_BACKEND_URL?.replace(/\/$/, '')
const backendToken = process.env.AI_TRADING_BACKEND_TOKEN
const backendTimeoutMs = Number(process.env.AI_TRADING_BACKEND_TIMEOUT_MS || 10_000)
const maxAgeMs = Number(process.env.TRADING_AMOUNT_MAX_AGE_SECONDS || 30 * 24 * 60 * 60) * 1000

function parseAmount(value: unknown): number | null {
  if (typeof value !== 'number' && typeof value !== 'string') return null
  const amount = Number(value)
  return Number.isFinite(amount) && amount > 0 ? Math.round(amount * 100) / 100 : null
}

async function backend(endpoint: string, init: RequestInit = {}) {
  if (!backendUrl) return null
  if (!backendToken) throw new Error('AI_TRADING_BACKEND_TOKEN is not configured')
  const headers = new Headers(init.headers)
  headers.set('Content-Type', 'application/json')
  headers.set('Authorization', `Bearer ${backendToken}`)
  const response = await fetch(`${backendUrl}${endpoint}`, {
    ...init,
    headers,
    cache: 'no-store',
    signal: init.signal || AbortSignal.timeout(backendTimeoutMs),
  })
  const payload = await response.json().catch(() => null)
  if (!response.ok) throw new Error(payload?.error || `Trading backend failed with ${response.status}`)
  return payload
}

async function authenticatedUser() {
  const supabase = await createClient()
  const { data: { user }, error } = await supabase.auth.getUser()
  if (error || !user) return { user: null, supabase }
  return { user, supabase }
}

async function localEntry(userId: string) {
  try {
    const state = JSON.parse(await fs.readFile(statePath, 'utf8'))
    return state?.user_states?.[userId] || {}
  } catch {
    return {}
  }
}

function responseFor(entry: any) {
  const configured = Boolean(entry?.enabled)
  const mode = String(entry?.trade_mode || (entry?.trade_amount !== null && entry?.trade_amount !== undefined && entry?.trade_amount !== '' ? 'manual' : 'auto'))
  if (mode === 'auto') return {
    configured,
    eligible: configured,
    trade_mode: 'auto',
    status_code: configured ? 'automatic_balance' : 'automatic_balance_not_saved',
    message: configured
      ? 'Automatic sizing is active. Available broker balance will be checked for each event.'
      : 'Leave the amount blank and save to use your available broker balance automatically.',
    trade_amount: null,
    amount_updated_at_utc: entry?.amount_updated_at_utc || null,
  }
  const amount = parseAmount(entry?.trade_amount)
  const updatedAt = Date.parse(String(entry?.amount_updated_at_utc || ''))
  if (!amount) return { configured, eligible: false, trade_mode: 'manual', status_code: 'amount_missing_or_invalid', message: 'The saved manual amount is invalid. Enter a positive amount or leave it blank for automatic sizing.', trade_amount: null }
  if (!Number.isFinite(updatedAt)) return { eligible: false, status_code: 'amount_timestamp_unavailable', message: 'The saved trading amount cannot be verified. Save it again.', trade_amount: amount }
  if (Date.now() - updatedAt > maxAgeMs) return { eligible: false, status_code: 'amount_stale', message: 'The saved trading amount is stale. Review and save it again.', trade_amount: amount, amount_updated_at_utc: entry.amount_updated_at_utc }
  return { configured, eligible: configured, trade_mode: 'manual', status_code: 'manual_amount', message: 'Manual trading amount saved. Live monitoring continues automatically.', trade_amount: amount, amount_updated_at_utc: entry.amount_updated_at_utc }
}

export async function GET() {
  const { user } = await authenticatedUser()
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  try {
    const remote = await backend(`/ai-trading/config?user_id=${encodeURIComponent(user.id)}`)
    if (remote) return NextResponse.json({ ...remote, configured: Boolean(remote.enabled), eligible: Boolean(remote.enabled && remote.eligible), status_code: remote.code || remote.status_code })
  } catch (error) {
    console.warn('[Trading config] Backend unavailable:', error)
    if (backendUrl) {
      return NextResponse.json({ error: 'Trading backend unavailable' }, { status: 502 })
    }
  }
  return NextResponse.json(responseFor(await localEntry(user.id)))
}

export async function POST(request: NextRequest) {
  const { user, supabase } = await authenticatedUser()
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  const body = await request.json().catch(() => ({}))
  const rawAmount = body?.trade_amount
  const automatic = rawAmount === null || rawAmount === undefined || rawAmount === ''
  const amount = automatic ? null : parseAmount(rawAmount)
  if (!automatic && !amount) return NextResponse.json({ error: 'Enter a trading amount greater than zero, or leave it blank for automatic sizing.' }, { status: 400 })
  const { error: updateError } = await supabase.from('user_trading_keys').update({ is_trading_enabled: true }).eq('user_id', user.id)
  if (updateError) return NextResponse.json({ error: 'Connect a valid broker account before saving a trading amount.' }, { status: 409 })
  const now = new Date().toISOString()
  const payload = { user_id: user.id, email: user.email, trade_mode: automatic ? 'auto' : 'manual', trade_amount: amount, amount_updated_at_utc: now }
  try {
    const remote = await backend('/ai-trading/config', { method: 'POST', body: JSON.stringify(payload) })
    if (remote) return NextResponse.json({ ok: true, ...responseFor(remote.config) })
  } catch (error) {
    console.warn('[Trading config] Backend unavailable:', error)
    if (backendUrl) {
      return NextResponse.json({ error: 'Trading backend unavailable' }, { status: 502 })
    }
  }
  let state: any = { generated_at_utc: null, enabled_user_ids: [], user_states: {} }
  try { state = JSON.parse(await fs.readFile(statePath, 'utf8')) } catch {}
  state.user_states ||= {}
  state.user_states[user.id] = { ...(state.user_states[user.id] || {}), enabled: true, email: user.email, trade_mode: automatic ? 'auto' : 'manual', trade_amount: amount, amount_updated_at_utc: now, updated_at_utc: now }
  state.enabled_user_ids = Object.entries(state.user_states).filter(([, value]: any) => Boolean(value?.enabled)).map(([id]) => id).sort()
  state.generated_at_utc = now
  await fs.mkdir(path.dirname(statePath), { recursive: true })
  await fs.writeFile(statePath, JSON.stringify(state, null, 2), 'utf8')
  return NextResponse.json({ ok: true, ...responseFor(state.user_states[user.id]) })
}
