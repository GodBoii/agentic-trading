import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import { convexAdminMutation, convexAdminQuery } from '@/lib/convex/server'
import { AUTO_TRADE_SLOTS } from '@/lib/trade-sizing'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

const maxAgeMs = Number(process.env.TRADING_AMOUNT_MAX_AGE_SECONDS || 30 * 24 * 60 * 60) * 1000
const maxLeverage = 5

interface TradingConfiguration {
  supabaseUserId: string
  enabled: boolean
  tradeMode: 'auto' | 'manual'
  tradeAmount?: number
  amountUpdatedAt?: string
  statusCode?: string
  updatedAt: string
}

interface OrderPlacementState {
  allowed: boolean
  statusCode: string
  reason: string
  verifiedAt: string
  nextVerificationAt: string
  detectedIp?: string
  primaryIp?: string
  secondaryIp?: string
  ordersAllowed?: boolean
}

function parseAmount(value: unknown): number | null {
  if (typeof value !== 'number' && typeof value !== 'string') return null
  const amount = Number(value)
  return Number.isFinite(amount) && amount > 0 ? Math.round(amount * 100) / 100 : null
}

async function authenticatedUser() {
  const supabase = await createClient()
  const { data: { user }, error } = await supabase.auth.getUser()
  return { user: error ? null : user, supabase }
}

function orderPlacementResponse(state: OrderPlacementState | null) {
  return {
    allowed: Boolean(state?.allowed),
    status_code: state?.statusCode || 'ORDER_PLACEMENT_UNKNOWN',
    reason: state?.reason || 'order_placement_not_verified',
    verified_at_utc: state?.verifiedAt || null,
    next_verification_at_utc: state?.nextVerificationAt || null,
    detected_ip: state?.detectedIp || null,
    primary_ip: state?.primaryIp || null,
    secondary_ip: state?.secondaryIp || null,
    orders_allowed: state?.ordersAllowed ?? null,
  }
}

function responseFor(entry: TradingConfiguration | null, orderPlacement: OrderPlacementState | null) {
  const sizingPolicy = { auto_slots: AUTO_TRADE_SLOTS, max_leverage: maxLeverage }
  const configured = Boolean(entry?.enabled)
  const mode = entry?.tradeMode || 'auto'
  if (mode === 'auto') return {
    configured,
    eligible: configured,
    trade_mode: 'auto',
    status_code: configured ? 'automatic_balance' : 'automatic_balance_not_saved',
    message: configured
      ? `Automatic sizing is active. Available margin is split across ${AUTO_TRADE_SLOTS} trade slots.`
      : `Save Auto to split available margin across ${AUTO_TRADE_SLOTS} trade slots.`,
    trade_amount: null,
    ...sizingPolicy,
    amount_updated_at_utc: entry?.amountUpdatedAt || null,
    order_placement: orderPlacementResponse(orderPlacement),
  }
  const amount = parseAmount(entry?.tradeAmount)
  const updatedAt = Date.parse(String(entry?.amountUpdatedAt || ''))
  if (!amount) return { configured, eligible: false, trade_mode: 'manual', status_code: 'amount_missing_or_invalid', message: 'The saved manual margin allocation is invalid. Enter a positive amount or use automatic sizing.', trade_amount: null, ...sizingPolicy, order_placement: orderPlacementResponse(orderPlacement) }
  if (!Number.isFinite(updatedAt)) return { configured, eligible: false, trade_mode: 'manual', status_code: 'amount_timestamp_unavailable', message: 'The saved margin allocation cannot be verified. Save it again.', trade_amount: amount, ...sizingPolicy, order_placement: orderPlacementResponse(orderPlacement) }
  if (Date.now() - updatedAt > maxAgeMs) return { configured, eligible: false, trade_mode: 'manual', status_code: 'amount_stale', message: 'The saved margin allocation is stale. Review and save it again.', trade_amount: amount, ...sizingPolicy, amount_updated_at_utc: entry?.amountUpdatedAt, order_placement: orderPlacementResponse(orderPlacement) }
  return { configured, eligible: configured, trade_mode: 'manual', status_code: 'manual_amount', message: 'Manual margin allocation saved. Live monitoring continues automatically.', trade_amount: amount, ...sizingPolicy, amount_updated_at_utc: entry?.amountUpdatedAt, order_placement: orderPlacementResponse(orderPlacement) }
}

export async function GET() {
  const { user } = await authenticatedUser()
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  try {
    const [entry, orderPlacement] = await Promise.all([
      convexAdminQuery<TradingConfiguration | null>('tradingConfigurations:get', {
        supabaseUserId: user.id,
      }),
      convexAdminQuery<OrderPlacementState | null>('orderPlacementStates:get', { broker: 'dhan' }),
    ])
    return NextResponse.json(responseFor(entry, orderPlacement))
  } catch (error) {
    console.error('[Trading config] Convex read failed:', error)
    return NextResponse.json({ error: 'Trading configuration storage unavailable' }, { status: 503 })
  }
}

export async function POST(request: NextRequest) {
  const { user, supabase } = await authenticatedUser()
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const body = await request.json().catch(() => ({}))
  const rawAmount = body?.trade_amount
  const automatic = rawAmount === null || rawAmount === undefined || rawAmount === ''
  const amount = automatic ? null : parseAmount(rawAmount)
  if (!automatic && !amount) {
    return NextResponse.json(
      { error: 'Enter a margin allocation greater than zero, or use automatic sizing.' },
      { status: 400 },
    )
  }

  // Supabase remains the source for identity and broker-connection metadata.
  const { data: brokerConnection, error: brokerError } = await supabase
    .from('user_trading_keys')
    .select('user_id')
    .eq('user_id', user.id)
    .maybeSingle()
  if (brokerError || !brokerConnection) {
    return NextResponse.json(
      { error: 'Connect a valid broker account before saving a trading amount.' },
      { status: 409 },
    )
  }

  const now = new Date().toISOString()
  try {
    const entry = await convexAdminMutation<TradingConfiguration>(
      'tradingConfigurations:upsert',
      {
        supabaseUserId: user.id,
        enabled: true,
        tradeMode: automatic ? 'auto' : 'manual',
        ...(automatic ? { clearTradeAmount: true } : { tradeAmount: amount }),
        amountUpdatedAt: now,
        statusCode: automatic ? 'automatic_balance' : 'manual_amount',
        updatedAt: now,
      },
    )
    const orderPlacement = await convexAdminQuery<OrderPlacementState | null>(
      'orderPlacementStates:get',
      { broker: 'dhan' },
    )
    return NextResponse.json({ ok: true, ...responseFor(entry, orderPlacement) })
  } catch (error) {
    console.error('[Trading config] Convex write failed:', error)
    return NextResponse.json({ error: 'Trading configuration storage unavailable' }, { status: 503 })
  }
}
