import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'

export async function GET(request: NextRequest) {
    console.log('[DhanCb] Starting Callback Request')
    try {
        // 1. Extract tokenId from query parameters
        const { searchParams } = new URL(request.url)
        const tokenId = searchParams.get('tokenId')
        
        console.log(`[DhanCb] TokenId received: ${tokenId ? 'YES' : 'NO'}`)

        if (!tokenId) {
            console.error('[DhanCb] Missing tokenId')
            return NextResponse.redirect(
                new URL('/dashboard?error=missing_token', request.url)
            )
        }

        // 2. Verify user is authenticated
        const supabase = await createClient()
        const { data: { user }, error: authError } = await supabase.auth.getUser()
        
        if (authError || !user) {
            console.error('[DhanCb] Auth Error:', authError)
            return NextResponse.redirect(
                new URL('/login?error=unauthorized_callback', request.url)
            )
        }
        console.log(`[DhanCb] User Authenticated: ${user.id}`)

        // 3. Get Dhan credentials from environment
        const DHAN_APP_ID = process.env.DHAN_APP_ID
        const DHAN_APP_SECRET = process.env.DHAN_APP_SECRET
        
        // Log existence only, not values
        console.log(`[DhanCb] Env Vars Check - ID: ${!!DHAN_APP_ID}, Secret: ${!!DHAN_APP_SECRET}`)

        if (!DHAN_APP_ID || !DHAN_APP_SECRET) {
            console.error('[DhanCb] Missing Env Vars')
            return NextResponse.redirect(
                new URL('/dashboard?error=server_config_missing_vars', request.url)
            )
        }

        // 4. Exchange tokenId for access token using correct Dhan v2.0 endpoint
        const dhanTokenUrl = `https://auth.dhan.co/app/consumeApp-consent?tokenId=${tokenId}`
        console.log('[DhanCb] Fetching tokens from:', dhanTokenUrl)

        const dhanResponse = await fetch(dhanTokenUrl, {
            headers: {
                'app_id': DHAN_APP_ID,
                'app_secret': DHAN_APP_SECRET,
                'User-Agent': 'TraderApp/1.0',
            },
        })
        
        console.log(`[DhanCb] Dhan Response Status: ${dhanResponse.status}`)

        if (!dhanResponse.ok) {
            const errorText = await dhanResponse.text()
            console.error('[DhanCb] Token Exchange Failed:', errorText)
            const safeError = encodeURIComponent(errorText.substring(0, 200))
            return NextResponse.redirect(
                new URL(`/dashboard?error=token_exchange_failed&details=${safeError}`, request.url)
            )
        }

        const dhanData = await dhanResponse.json()
        console.log('[DhanCb] Dhan Data Keys:', Object.keys(dhanData))

        // Validate the response
        if (!dhanData.accessToken || !dhanData.dhanClientId) {
            console.error('[DhanCb] Invalid Response Structure:', dhanData)
            return NextResponse.redirect(
                new URL('/dashboard?error=invalid_response_structure', request.url)
            )
        }

        // 5. Calculate token expiry (Dhan tokens typically last 30 days)
        const tokenExpiry = new Date()
        tokenExpiry.setDate(tokenExpiry.getDate() + 30)

        // 6. Store credentials in Supabase using UPSERT
        console.log('[DhanCb] Upserting to Supabase...')
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
            console.error('[DhanCb] DB Insert Failed:', dbError)
            const safeDbError = encodeURIComponent(dbError.message || 'Unknown database error')
            return NextResponse.redirect(
                new URL(`/dashboard?error=db_save_failed&details=${safeDbError}`, request.url)
            )
        }
        
        console.log('[DhanCb] Success! Redirecting...')

        // 7. Redirect to dashboard with success flag
        return NextResponse.redirect(
            new URL('/dashboard?success=true', request.url)
        )

    } catch (error) {
        console.error('[DhanCb] Unexpected Error:', error)
        const errorMessage = error instanceof Error ? error.message : 'Unknown error'
        return NextResponse.redirect(
            new URL(`/dashboard?error=unexpected&details=${encodeURIComponent(errorMessage)}`, request.url)
        )
    }
}
