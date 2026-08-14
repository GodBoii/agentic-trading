import { NextResponse } from 'next/server'
import { listTradeSessions } from '@/lib/ai-trading-sessions'
import { createClient } from '@/lib/supabase/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET() {
  try {
    const supabase = await createClient()
    const { data: { user }, error: authError } = await supabase.auth.getUser()
    if (authError || !user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }
    return NextResponse.json({ sessions: await listTradeSessions(user.id) })
  } catch (error) {
    console.error('AI trading sessions list error:', error)
    return NextResponse.json({ error: 'Failed to load trade sessions' }, { status: 500 })
  }
}
