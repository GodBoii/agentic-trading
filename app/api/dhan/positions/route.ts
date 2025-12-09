import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'

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

        // 3. Fetch positions from Dhan API
        const dhanResponse = await fetch('https://api.dhan.co/v2/positions', {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                'access-token': tradingKeys.dhan_access_token,
            },
        })

        if (!dhanResponse.ok) {
            const errorText = await dhanResponse.text()
            console.error('Dhan API error:', errorText)
            return NextResponse.json(
                { error: 'Failed to fetch positions from Dhan' },
                { status: 500 }
            )
        }

        const positions = await dhanResponse.json()

        return NextResponse.json(positions)

    } catch (error) {
        console.error('Error fetching positions:', error)
        return NextResponse.json(
            { error: 'Internal server error' },
            { status: 500 }
        )
    }
}
