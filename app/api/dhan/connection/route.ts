import { NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function DELETE() {
    try {
        const supabase = await createClient()
        const { data: { user }, error: authError } = await supabase.auth.getUser()

        if (authError || !user) {
            return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
        }

        const { error } = await supabase
            .from('user_trading_keys')
            .delete()
            .eq('user_id', user.id)

        if (error) {
            console.error('Failed to disconnect Dhan account:', error)
            return NextResponse.json({ error: 'Unable to disconnect Dhan account' }, { status: 500 })
        }

        return NextResponse.json({ success: true })
    } catch (error) {
        console.error('Error disconnecting Dhan account:', error)
        return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
    }
}
