import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import { decryptDhanAccessToken, dhanApiHeaders, readDhanError } from '../_utils'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(request: NextRequest) {
    try {
        // 1. Verify user is authenticated
        const supabase = await createClient()
        const { data: { user }, error: authError } = await supabase.auth.getUser()

        if (authError || !user) {
            return NextResponse.json(
                { error: 'Unauthorized' },
                { status: 401 }
            )
        }

        // 2. Get user's Dhan access token from database
        const { data: tradingKeys, error: dbError } = await supabase
            .from('user_trading_keys')
            .select('dhan_access_token, dhan_client_id')
            .eq('user_id', user.id)
            .single()

        if (dbError || !tradingKeys) {
            return NextResponse.json(
                { error: 'Dhan account not connected' },
                { status: 404 }
            )
        }

        // 3. Fetch fund limits from Dhan API
        const dhanResponse = await fetch('https://api.dhan.co/v2/fundlimit', {
            method: 'GET',
            headers: dhanApiHeaders(decryptDhanAccessToken(tradingKeys.dhan_access_token)),
        })

        if (!dhanResponse.ok) {
            const { errorText, errorMessage } = await readDhanError(dhanResponse, 'Failed to fetch funds from Dhan')
            console.error('Dhan API error:', errorText)

            return NextResponse.json(
                { error: errorMessage },
                { status: dhanResponse.status } // Propagate the actual status code (e.g. 401)
            )
        }

        const funds = await dhanResponse.json()

        return NextResponse.json(funds)

    } catch (error) {
        console.error('Error fetching funds:', error)
        return NextResponse.json(
            { error: 'Internal server error' },
            { status: 500 }
        )
    }
}
