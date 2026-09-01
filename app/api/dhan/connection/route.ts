import { NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import { getStoredDhanCredentials, removeDhanCredentials } from '@/lib/dhan/user-credentials'
import { convexAdminMutation } from '@/lib/convex/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

async function userId() {
  const supabase = await createClient()
  const { data: { user }, error } = await supabase.auth.getUser()
  return error ? null : user?.id || null
}

export async function GET() {
  const id = await userId()
  if (!id) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  try {
    const credentials = await getStoredDhanCredentials(id)
    if (!credentials) return NextResponse.json({ connected: false })
    return NextResponse.json({
      connected: true,
      dhanClientId: credentials.dhanClientId,
      tokenExpiresAt: credentials.tokenExpiresAt || null,
      authorized: Boolean(
        credentials.encryptedAccessToken
          && credentials.tokenExpiresAt
          && Date.parse(credentials.tokenExpiresAt) > Date.now(),
      ),
    })
  } catch (error) {
    console.error('Dhan connection lookup failed:', error)
    return NextResponse.json({ error: 'Unable to check Dhan connection.' }, { status: 503 })
  }
}

export async function DELETE() {
  const supabase = await createClient()
  const { data: { user }, error: authError } = await supabase.auth.getUser()
  const id = authError ? null : user?.id || null
  if (!id) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  try {
    await removeDhanCredentials(id)
    await convexAdminMutation('tradingConfigurations:upsert', {
      supabaseUserId: id,
      enabled: false,
      statusCode: 'broker_disconnected',
      updatedAt: new Date().toISOString(),
    })
    await supabase.from('user_trading_keys').delete().eq('user_id', id)
    return NextResponse.json({ success: true })
  } catch (error) {
    console.error('Dhan disconnect failed:', error)
    return NextResponse.json({ error: 'Unable to disconnect Dhan.' }, { status: 500 })
  }
}
