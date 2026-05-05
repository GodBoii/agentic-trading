import { NextRequest, NextResponse } from 'next/server'
import { promises as fs } from 'fs'
import path from 'path'
import { createClient } from '@/lib/supabase/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

interface ToggleStatePayload {
  generated_at_utc: string | null
  enabled_user_ids: string[]
  user_states: Record<
    string,
    {
      enabled: boolean
      updated_at_utc: string
      email?: string | null
    }
  >
}

const stateFilePath = path.join(process.cwd(), 'python-backend', 'ai_trading_state.json')
const requestFilePath = path.join(process.cwd(), 'python-backend', 'ai_trading_request.json')
const statusFilePath = path.join(process.cwd(), 'python-backend', 'ai_trading_run_status.json')
const backendUrl = process.env.AI_TRADING_BACKEND_URL?.replace(/\/$/, '')
const backendToken = process.env.AI_TRADING_BACKEND_TOKEN

async function callTradingBackend(endpoint: string, init: RequestInit = {}) {
  if (!backendUrl) return null

  const headers = new Headers(init.headers)
  headers.set('Content-Type', 'application/json')
  if (backendToken) {
    headers.set('Authorization', `Bearer ${backendToken}`)
  }

  const response = await fetch(`${backendUrl}${endpoint}`, {
    ...init,
    headers,
    cache: 'no-store',
  })

  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    throw new Error(payload?.error || `AI trading backend failed with ${response.status}`)
  }
  return payload
}

async function loadState(): Promise<ToggleStatePayload> {
  try {
    const raw = await fs.readFile(stateFilePath, 'utf8')
    const parsed = JSON.parse(raw)
    return {
      generated_at_utc: parsed.generated_at_utc ?? null,
      enabled_user_ids: Array.isArray(parsed.enabled_user_ids) ? parsed.enabled_user_ids : [],
      user_states: typeof parsed.user_states === 'object' && parsed.user_states ? parsed.user_states : {},
    }
  } catch {
    return {
      generated_at_utc: null,
      enabled_user_ids: [],
      user_states: {},
    }
  }
}

async function saveState(state: ToggleStatePayload) {
  await fs.mkdir(path.dirname(stateFilePath), { recursive: true })
  await fs.writeFile(stateFilePath, JSON.stringify(state, null, 2), 'utf8')
}

async function writeStartRequest(user: { id: string; email?: string | null }) {
  const request = {
    request_id: `${Date.now()}-${user.id}`,
    action: 'start',
    user_id: user.id,
    email: user.email ?? null,
    requested_at_utc: new Date().toISOString(),
  }
  await fs.mkdir(path.dirname(requestFilePath), { recursive: true })
  await fs.writeFile(requestFilePath, JSON.stringify(request, null, 2), 'utf8')
  return request
}

async function loadRunStatus() {
  try {
    const raw = await fs.readFile(statusFilePath, 'utf8')
    return JSON.parse(raw)
  } catch {
    return {
      status: 'idle',
      current_stage: 'idle',
      message: null,
      stages: {
        stage2: { status: 'pending', summary: null, details: null },
        stock_analyzer: { status: 'pending', summary: null },
        risk_analyzer: { status: 'pending', summary: null },
        executioner: { status: 'pending', summary: null },
      },
    }
  }
}

export async function POST(request: NextRequest) {
  try {
    const supabase = await createClient()
    const {
      data: { user },
      error: authError,
    } = await supabase.auth.getUser()

    if (authError || !user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const body: { enabled?: boolean } = await request.json().catch(() => ({}))
    const enabled = body?.enabled === undefined ? true : Boolean(body?.enabled)

    const { error: updateError } = await supabase
      .from('user_trading_keys')
      .update({ is_trading_enabled: enabled })
      .eq('user_id', user.id)

    if (updateError) {
      console.error('Failed to update AI trading status in Supabase:', updateError)
      return NextResponse.json({ error: 'Failed to update trading status' }, { status: 500 })
    }

    const state = await loadState()
    state.user_states[user.id] = {
      enabled,
      updated_at_utc: new Date().toISOString(),
      email: user.email ?? null,
    }
    state.enabled_user_ids = Object.entries(state.user_states)
      .filter(([, value]) => Boolean(value?.enabled))
      .map(([userId]) => userId)
      .sort()
    state.generated_at_utc = new Date().toISOString()
    await saveState(state)
    const localRequest = {
      request_id: `${Date.now()}-${user.id}`,
      action: 'start',
      user_id: user.id,
      email: user.email ?? null,
      requested_at_utc: new Date().toISOString(),
    }
    const backendPayload = enabled
      ? await callTradingBackend('/ai-trading/start', {
        method: 'POST',
        body: JSON.stringify(localRequest),
      })
      : null
    const startRequest = enabled
      ? backendPayload?.request || await writeStartRequest({ id: user.id, email: user.email })
      : null

    return NextResponse.json({
      ok: true,
      enabled,
      enabled_user_ids: state.enabled_user_ids,
      request: startRequest,
    })
  } catch (error) {
    console.error('AI trading toggle route error:', error)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}

export async function GET() {
  try {
    const backendPayload = await callTradingBackend('/ai-trading/status', { method: 'GET' })
    if (backendPayload) {
      return NextResponse.json(backendPayload)
    }
    return NextResponse.json(await loadRunStatus())
  } catch (error) {
    console.error('AI trading status route error:', error)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}
