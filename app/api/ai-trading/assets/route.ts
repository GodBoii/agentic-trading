import { NextRequest, NextResponse } from 'next/server'
import { promises as fs } from 'fs'
import path from 'path'
import { resolveTradingArtifactPath } from '@/lib/ai-trading-sessions'
import { createClient } from '@/lib/supabase/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

const contentTypes: Record<string, string> = {
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.md': 'text/markdown; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
}

export async function GET(request: NextRequest) {
  try {
    const supabase = await createClient()
    const { data: { user }, error: authError } = await supabase.auth.getUser()
    if (authError || !user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const rawPath = request.nextUrl.searchParams.get('path')
    if (!rawPath) {
      return NextResponse.json({ error: 'Missing artifact path' }, { status: 400 })
    }

    const resolved = resolveTradingArtifactPath(rawPath)
    const body = await fs.readFile(resolved)
    const contentType = contentTypes[path.extname(resolved).toLowerCase()] || 'application/octet-stream'
    return new NextResponse(new Uint8Array(body), {
      headers: {
        'content-type': contentType,
        'cache-control': 'private, max-age=60',
      },
    })
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Artifact not found' },
      { status: 404 },
    )
  }
}
