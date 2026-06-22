import { NextResponse } from 'next/server'
import { listTradeSessions } from '@/lib/ai-trading-sessions'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET() {
  try {
    return NextResponse.json({ sessions: await listTradeSessions() })
  } catch (error) {
    console.error('AI trading sessions list error:', error)
    return NextResponse.json({ error: 'Failed to load trade sessions' }, { status: 500 })
  }
}
