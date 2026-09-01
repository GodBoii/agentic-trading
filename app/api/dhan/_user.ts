import { NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import { getDhanAccessCredentials } from '@/lib/dhan/user-credentials'
import { readDhanError } from './_utils'

export async function authenticatedDhanGet(
  path: string,
  options: { emptyMessage?: string } = {},
) {
  const supabase = await createClient()
  const { data: { user }, error: authError } = await supabase.auth.getUser()
  if (authError || !user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  try {
    const credentials = await getDhanAccessCredentials(user.id)
    if (!credentials) return NextResponse.json({ error: 'Dhan account not connected' }, { status: 404 })
    if (Date.parse(credentials.expiresAt) <= Date.now()) {
      return NextResponse.json({ error: 'Dhan authorization expired. Reconnect Dhan.' }, { status: 401 })
    }

    const response = await fetch(`https://api.dhan.co/v2${path}`, {
      headers: { 'Content-Type': 'application/json', 'access-token': credentials.accessToken },
      cache: 'no-store',
      signal: AbortSignal.timeout(8_000),
    })
    if (response.ok) return NextResponse.json(await response.json())

    const { errorJson, errorMessage } = await readDhanError(response, 'Dhan request failed')
    if (options.emptyMessage && errorJson.errorMessage === options.emptyMessage) {
      return NextResponse.json([])
    }
    return NextResponse.json({ error: errorMessage }, { status: response.status })
  } catch (error) {
    console.error(`Dhan request failed for ${path}:`, error)
    return NextResponse.json({ error: 'Unable to reach Dhan.' }, { status: 502 })
  }
}
