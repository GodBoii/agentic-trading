import { promises as fs } from 'fs'
import path from 'path'
import { createClient as createSupabaseClient } from '@supabase/supabase-js'

type JsonRecord = Record<string, any>

const rootDir = process.cwd()
const backendDir = path.join(rootDir, 'python-backend')
const sessionsDir = path.join(backendDir, 'ai_trading_sessions')
const statusPath = path.join(backendDir, 'ai_trading_run_status.json')
const stockAgentLatestPath = path.join(backendDir, 'stock_agent_latest.json')
const defaultBucket = process.env.SUPABASE_TRADE_SESSIONS_BUCKET || 'trade-sessions'

export function resolveTradingArtifactPath(input: string) {
  const normalized = decodeURIComponent(input).replaceAll('\\', '/')
  let candidate = normalized

  if (candidate.startsWith('/app/')) {
    candidate = path.join(rootDir, candidate.slice('/app/'.length))
  } else if (!path.isAbsolute(candidate)) {
    candidate = path.join(rootDir, candidate)
  }

  const resolved = path.resolve(candidate)
  const backendResolved = path.resolve(backendDir)
  if (resolved !== backendResolved && !resolved.startsWith(`${backendResolved}${path.sep}`)) {
    throw new Error('Artifact path is outside the trading backend directory')
  }
  return resolved
}

export async function loadTradeSession(sessionId: string) {
  const safeId = safeSegment(sessionId)
  if (!safeId) return null
  const localSession = await readJson(path.join(sessionsDir, safeId, 'session.json'))
  return localSession || loadTradeSessionFromSupabase(safeId)
}

export async function listTradeSessions() {
  await syncLatestTradeSession({ uploadToCloud: false })

  let entries: string[] = []
  try {
    entries = await fs.readdir(sessionsDir)
  } catch {
    entries = []
  }

  const localSessions = await Promise.all(
    entries.map(async (entry) => {
      const payload = await readJson(path.join(sessionsDir, entry, 'session.json'))
      if (!payload) return null
      return sessionSummary(payload, entry)
    }),
  )

  const cloudSessions = await listTradeSessionsFromSupabase()
  const merged = new Map<string, JsonRecord>()
  for (const session of cloudSessions) {
    if (session?.session_id) merged.set(String(session.session_id), session)
  }
  for (const session of localSessions.filter(Boolean) as JsonRecord[]) {
    if (session?.session_id) merged.set(String(session.session_id), session)
  }

  return Array.from(merged.values())
    .sort((a: any, b: any) => Date.parse(b.updated_at_utc || b.created_at_utc || '') - Date.parse(a.updated_at_utc || a.created_at_utc || ''))
}

export async function syncLatestTradeSession(options: { status?: JsonRecord | null; uploadToCloud?: boolean } = {}) {
  const status = options.status || await readJson(statusPath)
  if (!status || typeof status !== 'object') return null

  const requestId = String(status.request?.request_id || '').trim()
  if (!requestId) return null

  const sessionId = safeSegment(requestId)
  if (!sessionId) return null

  const sessionPath = path.join(sessionsDir, sessionId, 'session.json')
  const existing = await readJson(sessionPath)
  if (options.uploadToCloud && existing?.cloud_synced_at_utc && status.status === 'completed') {
    return existing
  }

  const stockPayload = await readJson(stockAgentLatestPath)
  const agents = await buildAgents(sessionId, stockPayload, status)
  const session = {
    session_id: sessionId,
    request_id: requestId,
    title: buildTitle(status, agents),
    status: status.status || 'unknown',
    created_at_utc: status.request?.requested_at_utc || null,
    updated_at_utc: status.updated_at_utc || new Date().toISOString(),
    request: status.request || {},
    summary: stockPayload?.summary || status.stages?.stock_agent?.summary || null,
    status_snapshot: hydrateStatusWithAgents(status, agents),
    agents,
    local_saved_at_utc: new Date().toISOString(),
    cloud_synced_at_utc: existing?.cloud_synced_at_utc || null,
  }

  await fs.mkdir(path.dirname(sessionPath), { recursive: true })
  await fs.writeFile(sessionPath, JSON.stringify(session, null, 2), 'utf8')

  if (options.uploadToCloud && status.status === 'completed') {
    await syncSessionImagesToSupabase(session)
    session.cloud_synced_at_utc = new Date().toISOString()
    await fs.writeFile(sessionPath, JSON.stringify(session, null, 2), 'utf8')
  }

  return session
}

async function buildAgents(sessionId: string, stockPayload: JsonRecord | null, status: JsonRecord) {
  const sourceResults = Array.isArray(stockPayload?.results)
    ? stockPayload.results
    : status.stages?.stock_agent?.details?.results || []

  return Promise.all(
    sourceResults.map(async (item: JsonRecord, index: number) => {
      const candidate = item.candidate || {}
      const rank = Number(item.rank || index + 1)
      const slug = slugify(candidate.display_name || item.display_name || candidate.symbol || `agent-${rank}`)
      const attachments = await materializeAttachments(sessionId, slug, rank, item)

      return {
        rank,
        symbol: candidate.symbol || item.symbol || null,
        display_name: candidate.display_name || item.display_name || candidate.symbol || `Agent ${rank}`,
        decision: item.decision || null,
        attachments,
        agent_metadata: item.agent_metadata || null,
        analysis: item.analysis || item.report_text || '',
        report_text: item.report_text || item.analysis || '',
      }
    }),
  )
}

async function materializeAttachments(sessionId: string, agentSlug: string, rank: number, item: JsonRecord) {
  const candidate = item.candidate || {}
  const chartArtifacts = candidate.chart_artifacts || {}
  const images = imageCards(chartArtifacts).map((image) => ({
    ...image,
    url: `/api/ai-trading/assets?path=${encodeURIComponent(String(image.path || ''))}`,
  }))

  const rawFiles = item.attachments?.files?.length
    ? item.attachments.files
    : fallbackFiles(item)

  const files = []
  for (const rawFile of rawFiles) {
    const filename = String(rawFile.filename || `${rawFile.id || 'file'}.md`)
    const localPath = path.join(sessionsDir, sessionId, agentSlug, filename)
    const content = String(rawFile.content || '')
    await fs.mkdir(path.dirname(localPath), { recursive: true })
    await fs.writeFile(localPath, content, 'utf8')
    files.push({
      id: rawFile.id || filename.replace(/\.md$/i, ''),
      title: rawFile.title || filename,
      filename,
      content_type: 'text/markdown',
      content,
      path: localPath,
      url: `/api/ai-trading/assets?path=${encodeURIComponent(localPath)}`,
      storage_path: `${sessionId}/agents/${rank}-${agentSlug}/${filename}`,
    })
  }

  return { images, files }
}

function imageCards(chartArtifacts: JsonRecord) {
  const charts = chartArtifacts?.charts && typeof chartArtifacts.charts === 'object' ? chartArtifacts.charts : {}
  const orderedPaths = Array.isArray(chartArtifacts?.chart_paths_ordered) ? chartArtifacts.chart_paths_ordered.map(String) : []
  const byPath = new Map<string, [string, JsonRecord]>()
  for (const [key, value] of Object.entries(charts)) {
    if (value && typeof value === 'object' && (value as JsonRecord).path) {
      byPath.set(String((value as JsonRecord).path), [key, value as JsonRecord])
    }
  }

  const ordered: Array<[string, JsonRecord]> = []
  for (const chartPath of orderedPaths) {
    const hit = byPath.get(chartPath)
    if (hit) ordered.push(hit)
  }
  for (const [key, value] of Object.entries(charts)) {
    if (!ordered.some(([existing]) => existing === key) && value && typeof value === 'object') {
      ordered.push([key, value as JsonRecord])
    }
  }

  return ordered.map(([key, value]) => ({
    id: key,
    title: `${titleCase(value.day_type || '')} ${value.label || ''}`.trim(),
    filename: String(value.path || '').replaceAll('\\', '/').split('/').pop() || `${key}.png`,
    path: value.path,
    day_type: value.day_type,
    date: value.date,
    timeframe: value.label,
    candles: value.candles,
    storage_path: '',
  }))
}

function fallbackFiles(item: JsonRecord) {
  const stock = item.selected_stock || {}
  const candidate = item.candidate || {}
  const stockPacket = item.stock_packet || {}
  return [
    {
      id: 'instructions',
      title: 'Instructions',
      filename: 'instructions.md',
      content: [
        `# ${stock.display_name || candidate.display_name || 'Stock'} Agent Instructions`,
        '',
        '- Analyze the assigned intraday stock candidate.',
        '- Use chart images and technical metadata as primary evidence.',
        '- Check Dhan margin and execution context before placement.',
        '- Return parseable Decision and Execution Status headers.',
        '',
        '## Selected Stock',
        '```json',
        JSON.stringify(stock, null, 2),
        '```',
      ].join('\n'),
    },
    {
      id: 'data',
      title: 'Data',
      filename: 'data.md',
      content: [
        `# ${stock.display_name || candidate.display_name || 'Stock'} Agent Data`,
        '',
        '```json',
        JSON.stringify({
          timing_context: stockPacket.timing_context,
          selected_stock: stock,
          stage2: candidate.stage2,
          technical_metadata: candidate.chart_artifacts?.technical_metadata,
          trade_config: stockPacket.trade_config,
        }, null, 2),
        '```',
      ].join('\n'),
    },
  ]
}

async function syncSessionImagesToSupabase(session: JsonRecord) {
  const client = serviceSupabase()
  if (!client) return

  for (const agent of session.agents || []) {
    const agentSlug = slugify(agent.display_name || agent.symbol || `agent-${agent.rank}`)
    for (const image of agent.attachments?.images || []) {
      if (image.cloud_url) continue
      try {
        const localPath = resolveTradingArtifactPath(String(image.path || ''))
        const storagePath = `${session.session_id}/agents/${agent.rank}-${agentSlug}/images/${image.filename}`
        const publicUrl = await uploadLocalFile(localPath, storagePath, 'image/png')
        image.storage_path = storagePath
        image.cloud_url = publicUrl
      } catch (error) {
        image.upload_error = error instanceof Error ? error.message : String(error)
      }
    }
  }
}

async function uploadLocalFile(localPath: string, storagePath: string, contentType: string) {
  const body = await fs.readFile(localPath)
  return uploadBuffer(body, storagePath, contentType)
}

async function uploadBuffer(body: Buffer, storagePath: string, contentType: string) {
  const client = serviceSupabase()
  if (!client) return null
  const { error } = await client.storage
    .from(defaultBucket)
    .upload(storagePath, body, { contentType, upsert: true })
  if (error) throw error
  const { data } = client.storage.from(defaultBucket).getPublicUrl(storagePath)
  return data.publicUrl
}

async function loadTradeSessionFromSupabase(sessionId: string) {
  const payload = await downloadJsonFromSupabase(`${sessionId}/session.json`)
  if (!payload) return null
  return {
    ...payload,
    loaded_from_cloud: true,
  }
}

async function listTradeSessionsFromSupabase() {
  const client = serviceSupabase()
  if (!client) return []

  const { data, error } = await client.storage
    .from(defaultBucket)
    .list('', { limit: 200, sortBy: { column: 'updated_at', order: 'desc' } })

  if (error || !Array.isArray(data)) return []

  const sessions = await Promise.all(
    data.map(async (entry) => {
      const sessionId = safeSegment(entry.name)
      if (!sessionId || entry.name === 'session.json') return null
      const payload = await downloadJsonFromSupabase(`${sessionId}/session.json`)
      return payload ? sessionSummary(payload, sessionId, true) : null
    }),
  )

  return sessions.filter(Boolean) as JsonRecord[]
}

async function downloadJsonFromSupabase(storagePath: string) {
  const client = serviceSupabase()
  if (!client) return null

  const { data, error } = await client.storage.from(defaultBucket).download(storagePath)
  if (error || !data) return null

  try {
    return JSON.parse(await data.text())
  } catch {
    return null
  }
}

function sessionSummary(payload: JsonRecord, fallbackId: string, loadedFromCloud = false) {
  return {
    session_id: payload.session_id || fallbackId,
    request_id: payload.request_id || payload.request?.request_id || fallbackId,
    title: payload.title || 'Trade session',
    status: payload.status || payload.status_snapshot?.status || 'unknown',
    created_at_utc: payload.created_at_utc || payload.request?.requested_at_utc || null,
    updated_at_utc: payload.updated_at_utc || payload.status_snapshot?.updated_at_utc || null,
    agent_count: Array.isArray(payload.agents) ? payload.agents.length : 0,
    executed_count: payload.summary?.executed_count ?? payload.status_snapshot?.stages?.stock_agent?.summary?.executed_count ?? 0,
    cloud_synced_at_utc: payload.cloud_synced_at_utc || null,
    loaded_from_cloud: loadedFromCloud,
  }
}

function serviceSupabase() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL
  const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY
  if (!url || !serviceRoleKey) return null
  return createSupabaseClient(url, serviceRoleKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  })
}

function hydrateStatusWithAgents(status: JsonRecord, agents: JsonRecord[]) {
  return {
    ...status,
    stages: {
      ...(status.stages || {}),
      stock_agent: {
        ...(status.stages?.stock_agent || {}),
        status: status.stages?.stock_agent?.status || (agents.length ? 'completed' : 'pending'),
        details: {
          ...(status.stages?.stock_agent?.details || {}),
          results: agents,
        },
      },
    },
  }
}

async function readJson(filePath: string) {
  try {
    return JSON.parse(await fs.readFile(filePath, 'utf8'))
  } catch {
    return null
  }
}

function safeSegment(value: string) {
  return String(value || '').replace(/[^A-Za-z0-9_.-]+/g, '-').replace(/^-+|-+$/g, '')
}

function slugify(value: string) {
  return safeSegment(String(value || '').toLowerCase()) || 'agent'
}

function titleCase(value: any) {
  return String(value || '').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function buildTitle(status: JsonRecord, agents: JsonRecord[]) {
  const names = agents.slice(0, 3).map((agent) => agent.display_name || agent.symbol).filter(Boolean)
  if (names.length) return names.join(', ')
  return status.request?.requested_at_utc ? `Trade session ${status.request.requested_at_utc}` : 'Trade session'
}
