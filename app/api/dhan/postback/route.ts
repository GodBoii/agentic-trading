import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@supabase/supabase-js'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

function serviceSupabase() {
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL
    const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY
    if (!url || !serviceRoleKey) {
        return null
    }
    return createClient(url, serviceRoleKey, {
        auth: {
            persistSession: false,
            autoRefreshToken: false,
        },
    })
}

export async function POST(request: NextRequest) {
    let payload: any
    try {
        payload = await request.json()
    } catch (error) {
        return NextResponse.json({ error: 'Invalid JSON payload' }, { status: 400 })
    }

    if (!payload || typeof payload !== 'object' || !payload.dhanClientId || !payload.orderId) {
        return NextResponse.json({ error: 'Invalid Dhan postback payload' }, { status: 400 })
    }

    const supabase = serviceSupabase()
    if (!supabase) {
        console.warn('Dhan postback received without SUPABASE_SERVICE_ROLE_KEY; payload acknowledged but not persisted')
        return NextResponse.json({ success: true, persisted: false })
    }

    const { error } = await supabase
        .from('dhan_order_postbacks')
        .insert({
            dhan_client_id: String(payload.dhanClientId),
            order_id: String(payload.orderId),
            correlation_id: payload.correlationId ? String(payload.correlationId) : null,
            order_status: payload.orderStatus ? String(payload.orderStatus) : null,
            payload,
            received_at: new Date().toISOString(),
        })

    if (error) {
        console.error('Failed to persist Dhan postback:', error)
        return NextResponse.json({ success: true, persisted: false })
    }

    return NextResponse.json({ success: true, persisted: true })
}
