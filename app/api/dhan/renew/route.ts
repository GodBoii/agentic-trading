import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import { decryptDhanAccessToken, encryptDhanAccessToken, parseDhanExpiryIso, readDhanError } from '../_utils'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function POST(request: NextRequest) {
    try {
        const supabase = await createClient()
        const { data: { user }, error: authError } = await supabase.auth.getUser()

        if (authError || !user) {
            return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
        }

        const { data: tradingKeys, error: dbError } = await supabase
            .from('user_trading_keys')
            .select('dhan_access_token, dhan_client_id')
            .eq('user_id', user.id)
            .single()

        if (dbError || !tradingKeys) {
            return NextResponse.json({ error: 'Dhan account not connected' }, { status: 404 })
        }

        const currentToken = decryptDhanAccessToken(tradingKeys.dhan_access_token)
        const dhanResponse = await fetch('https://api.dhan.co/v2/RenewToken', {
            method: 'GET',
            headers: {
                'access-token': currentToken,
                'dhanClientId': tradingKeys.dhan_client_id,
            },
        })

        if (!dhanResponse.ok) {
            const { errorText, errorMessage } = await readDhanError(dhanResponse, 'Failed to renew Dhan token')
            console.error('Dhan renew token error:', errorText)
            return NextResponse.json({ error: errorMessage }, { status: dhanResponse.status })
        }

        const dhanData = await dhanResponse.json()
        const renewedToken = dhanData.accessToken || dhanData.token || dhanData.data?.accessToken
        const tokenExpiryIso = parseDhanExpiryIso(dhanData.expiryTime || dhanData.data?.expiryTime)

        if (!renewedToken || !tokenExpiryIso) {
            console.error('Invalid Dhan renew response:', dhanData)
            return NextResponse.json({ error: 'Invalid response from Dhan token renewal' }, { status: 502 })
        }

        const { error: updateError } = await supabase
            .from('user_trading_keys')
            .update({
                dhan_access_token: encryptDhanAccessToken(renewedToken),
                token_expiry: tokenExpiryIso,
                updated_at: new Date().toISOString(),
            })
            .eq('user_id', user.id)

        if (updateError) {
            console.error('Failed to store renewed Dhan token:', updateError)
            return NextResponse.json({ error: 'Failed to store renewed Dhan token' }, { status: 500 })
        }

        return NextResponse.json({ success: true, token_expiry: tokenExpiryIso })
    } catch (error) {
        console.error('Error renewing Dhan token:', error)
        return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
    }
}
