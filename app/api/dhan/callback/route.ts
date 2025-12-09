import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'

export async function GET(request: NextRequest) {
    try {
        // 1. Extract tokenId from query parameters
        const { searchParams } = new URL(request.url)
        const tokenId = searchParams.get('tokenId')

        if (!tokenId) {
            return NextResponse.redirect(
                new URL('/dashboard?error=missing_token', request.url)
            )
        }

        // 2. Verify user is authenticated
        const supabase = await createClient()
        const { data: { user }, error: authError } = await supabase.auth.getUser()

        if (authError || !user) {
            return NextResponse.redirect(
                new URL('/login?error=unauthorized', request.url)
            )
        }

        // 3. Get Dhan credentials from environment
        const DHAN_APP_ID = process.env.DHAN_APP_ID
        const DHAN_APP_SECRET = process.env.DHAN_APP_SECRET

        if (!DHAN_APP_ID || !DHAN_APP_SECRET) {
            console.error('Missing Dhan credentials in environment variables')
            return NextResponse.redirect(
                new URL('/dashboard?error=server_config', request.url)
            )
        }

        // 4. Exchange tokenId for access token using correct Dhan v2.0 endpoint
        const dhanTokenUrl = `https://auth.dhan.co/app/consumeApp-consent?tokenId=${tokenId}`

        const dhanResponse = await fetch(dhanTokenUrl, {
            headers: {
                'app_id': DHAN_APP_ID,
                'app_secret': DHAN_APP_SECRET,
            },
        })

        if (!dhanResponse.ok) {
            const errorText = await dhanResponse.text()
            console.error('Dhan token exchange error:', errorText)
            return NextResponse.redirect(
                new URL('/dashboard?error=token_exchange_failed', request.url)
            )
        }

        const dhanData = await dhanResponse.json()

        // Validate the response
        if (!dhanData.accessToken || !dhanData.dhanClientId) {
            console.error('Invalid Dhan response:', dhanData)
            return NextResponse.redirect(
                new URL('/dashboard?error=invalid_response', request.url)
            )
        }

        // 5. Calculate token expiry (Dhan tokens typically last 30 days)
        const tokenExpiry = new Date()
        tokenExpiry.setDate(tokenExpiry.getDate() + 30)

        // 6. Store credentials in Supabase using UPSERT
        const { error: dbError } = await supabase
            .from('user_trading_keys')
            .upsert({
                user_id: user.id,
                dhan_client_id: dhanData.dhanClientId,
                dhan_access_token: dhanData.accessToken,
                token_expiry: tokenExpiry.toISOString(),
                is_trading_enabled: false, // Default to disabled for safety
                updated_at: new Date().toISOString(),
            }, {
                onConflict: 'user_id',
            })

        if (dbError) {
            console.error('Database error:', dbError)
            return NextResponse.redirect(
                new URL('/dashboard?error=db_save_failed', request.url)
            )
        }

        // 7. Redirect to dashboard with success flag
        return NextResponse.redirect(
            new URL('/dashboard?success=true', request.url)
        )

    } catch (error) {
        console.error('Error in dhan callback route:', error)
        return NextResponse.redirect(
            new URL('/dashboard?error=unexpected', request.url)
        )
    }
}
