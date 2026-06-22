import { NextRequest, NextResponse } from 'next/server'
import { loadTradeSession } from '@/lib/ai-trading-sessions'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(
  _request: NextRequest,
  { params }: { params: { sessionId: string } },
) {
  try {
    const session = await loadTradeSession(params.sessionId)
    if (!session) {
      return NextResponse.json({ error: 'Trade session not found' }, { status: 404 })
    }
    return NextResponse.json(session)
  } catch (error) {
    console.error('AI trading session read error:', error)
    return NextResponse.json({ error: 'Failed to load trade session' }, { status: 500 })
  }
}
