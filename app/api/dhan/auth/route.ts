import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'

export async function POST(request: NextRequest) {
    try {
        // 1. Verify user is authenticated
        const supabase = await createClient()
        const { data: { user }, error: authError } = await supabase.auth.getUser()

        if (authError || !user) {
            return NextResponse.json(
                { error: 'Unauthorized - Please login first' },
                { status: 401 }
            )
        }

        // 2. Get dhanClientId from request body
        const body = await request.json()
        const { dhanClientId } = body

        if (!dhanClientId || dhanClientId.trim() === '') {
            return NextResponse.json(
                { error: 'Dhan Client ID is required' },
                { status: 400 }
            )
        }

        // 3. Get Dhan credentials from environment
        const DHAN_APP_ID = process.env.DHAN_APP_ID
        const DHAN_APP_SECRET = process.env.DHAN_APP_SECRET
        const APP_URL = process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000'

        if (!DHAN_APP_ID || !DHAN_APP_SECRET) {
            console.error('Missing Dhan credentials in environment variables')
            return NextResponse.json(
                { error: 'Server configuration error' },
                { status: 500 }
            )
        }

        // 4. Make request to Dhan to generate consent
        const dhanAuthUrl = `https://auth.dhan.co/app/generate-consent?client_id=${dhanClientId}`

        const dhanResponse = await fetch(dhanAuthUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'app_id': DHAN_APP_ID,
                'app_secret': DHAN_APP_SECRET,
            },

        })

        if (!dhanResponse.ok) {
            const errorText = await dhanResponse.text()
            console.error('Dhan API error:', errorText)
            return NextResponse.json(
                { error: 'Failed to initiate Dhan authentication' },
                { status: 500 }
            )
        }

        const dhanData = await dhanResponse.json()

        // 5. Construct the login URL with consentId
        if (!dhanData.consentAppId) {
            console.error('No consentAppId received from Dhan:', dhanData)
            return NextResponse.json(
                { error: 'Invalid response from Dhan' },
                { status: 500 }
            )
        }

        const loginUrl = `https://auth.dhan.co/login/consentApp-login?consentAppId=${dhanData.consentAppId}`

        // 6. Return the URL to frontend
        return NextResponse.json({ url: loginUrl })

    } catch (error) {
        console.error('Error in dhan auth route:', error)
        return NextResponse.json(
            { error: 'Internal server error' },
            { status: 500 }
        )
    }
}
