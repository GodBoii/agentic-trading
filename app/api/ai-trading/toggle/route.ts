import { NextRequest, NextResponse } from 'next/server'
import { promises as fs } from 'fs'
import path from 'path'
import { createClient } from '@/lib/supabase/server'

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

    const body = await request.json()
    const enabled = Boolean(body?.enabled)

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

    return NextResponse.json({
      ok: true,
      enabled,
      enabled_user_ids: state.enabled_user_ids,
    })
  } catch (error) {
    console.error('AI trading toggle route error:', error)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}
