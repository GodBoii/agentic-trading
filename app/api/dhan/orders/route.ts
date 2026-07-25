import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import { decryptDhanAccessToken, dhanApiHeaders, readDhanError } from '../_utils'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(_request: NextRequest) {
    try {
        const supabase = await createClient()
        const { data: { user }, error: authError } = await supabase.auth.getUser()

        if (authError || !user) {
            return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
        }

        const { data: tradingKeys, error: dbError } = await supabase
            .from('user_trading_keys')
            .select('dhan_access_token')
            .eq('user_id', user.id)
            .single()

        if (dbError || !tradingKeys) {
            return NextResponse.json({ error: 'Dhan account not connected' }, { status: 404 })
        }

        const dhanResponse = await fetch('https://api.dhan.co/v2/orders', {
            method: 'GET',
            headers: dhanApiHeaders(decryptDhanAccessToken(tradingKeys.dhan_access_token)),
        })

        if (!dhanResponse.ok) {
            const { errorText, errorJson, errorMessage } = await readDhanError(
                dhanResponse,
                'Failed to fetch orders from Dhan',
            )
            console.error('Dhan orders API error:', errorText)

            if (errorJson.errorCode === 'DH-1111' || errorJson.errorMessage === 'No orders available') {
                return NextResponse.json([])
            }

            return NextResponse.json({ error: errorMessage }, { status: dhanResponse.status })
        }

        return NextResponse.json(await dhanResponse.json())
    } catch (error) {
        console.error('Error fetching orders:', error)
        return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
    }
}
