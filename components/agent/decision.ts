import { humanizeKey } from '@/lib/format'

/**
 * Interprets an agent's `decision` payload.
 *
 * The backend sends `Record<string, any>`, and the previous UI rendered it as
 * `Object.entries(decision).slice(0, 8)` — an undifferentiated grid where the
 * entry price, a boolean flag and a 400-word rationale all got the same 9px
 * label and the same cell. Which eight keys you saw depended on object key
 * order, and anything past the eighth was silently dropped.
 *
 * This resolves the payload into a hierarchy instead: the verdict, the trade
 * plan (which supports a derived risk/reward), remaining scalars, and prose.
 * Nothing is dropped, and unrecognized keys still render — just with the
 * weight they deserve.
 */

/** Key aliases, in priority order. Backends vary; the UI should not care. */
const FIELD_ALIASES = {
    action: ['action', 'side', 'signal', 'decision', 'recommendation', 'verdict', 'trade_action'],
    symbol: ['symbol', 'ticker', 'trading_symbol', 'instrument'],
    entry: ['entry_price', 'entry', 'buy_price', 'entry_level', 'price'],
    stop: ['stop_loss', 'stoploss', 'stop', 'sl', 'stop_price'],
    target: ['target', 'target_price', 'take_profit', 'tp', 'target_level'],
    quantity: ['quantity', 'qty', 'size', 'shares', 'position_size'],
    confidence: ['confidence', 'confidence_score', 'conviction', 'score'],
    capital: ['capital_required', 'capital', 'investment', 'amount', 'notional'],
} as const

type FieldName = keyof typeof FIELD_ALIASES

/** Values longer than this are prose, not a table cell. */
const PROSE_LENGTH = 140

export interface DecisionField {
    key: string
    label: string
    value: string
}

export interface DecisionPlan {
    entry?: number
    stop?: number
    target?: number
    /** Absolute per-unit loss if the stop is hit. */
    risk?: number
    /** Absolute per-unit gain if the target is hit. */
    reward?: number
    /** reward ÷ risk. Undefined unless both legs are known and risk is non-zero. */
    riskReward?: number
    /** A short setup has its target below entry. */
    direction?: 'long' | 'short'
}

export interface InterpretedDecision {
    action?: string
    /** 'buy' | 'sell' | 'hold' | 'none' — normalized for tone selection. */
    intent: 'buy' | 'sell' | 'hold' | 'none' | 'unknown'
    symbol?: string
    quantity?: number
    capital?: number
    /** Percentage, 0–100, normalized from either 0–1 or 0–100 input. */
    confidence?: number
    plan: DecisionPlan
    /** Remaining scalar fields, in payload order. */
    fields: DecisionField[]
    /** Long-form fields, keyed by humanized label. */
    prose: { key: string; label: string; text: string }[]
    isEmpty: boolean
}

function isScalar(value: unknown) {
    return value === null || ['string', 'number', 'boolean'].includes(typeof value)
}

function toNumber(value: unknown): number | undefined {
    if (typeof value === 'number' && Number.isFinite(value)) return value
    if (typeof value === 'string') {
        // Tolerates "₹1,234.50" and "1234.5 INR".
        const cleaned = value.replace(/[^0-9.\-]/g, '')
        if (cleaned && cleaned !== '-' && cleaned !== '.') {
            const parsed = Number(cleaned)
            if (Number.isFinite(parsed)) return parsed
        }
    }
    return undefined
}

function formatScalar(value: unknown): string {
    if (value === null || value === undefined || value === '') return '—'
    if (typeof value === 'boolean') return value ? 'Yes' : 'No'
    if (typeof value === 'number') {
        return Number.isInteger(value) ? String(value) : value.toFixed(2)
    }
    return String(value)
}

function normalizeIntent(action?: string): InterpretedDecision['intent'] {
    if (!action) return 'unknown'
    const text = action.toLowerCase()
    if (/no[\s_-]?trade|skip|avoid|reject|stand[\s_-]?aside/.test(text)) return 'none'
    if (/\bbuy\b|\blong\b|enter|accumulate/.test(text)) return 'buy'
    if (/\bsell\b|\bshort\b|exit|reduce/.test(text)) return 'sell'
    if (/hold|wait|watch|monitor/.test(text)) return 'hold'
    return 'unknown'
}

export function interpretDecision(decision?: Record<string, unknown> | null): InterpretedDecision {
    const consumed = new Set<string>()
    const source = decision || {}
    const lookup = new Map<string, string>()
    for (const key of Object.keys(source)) lookup.set(key.toLowerCase(), key)

    /** Resolve the first alias present in the payload and mark it consumed. */
    const take = (field: FieldName): unknown => {
        for (const alias of FIELD_ALIASES[field]) {
            const actual = lookup.get(alias)
            if (actual !== undefined && !consumed.has(actual) && isScalar(source[actual])) {
                consumed.add(actual)
                return source[actual]
            }
        }
        return undefined
    }

    const actionRaw = take('action')
    const action = actionRaw === null || actionRaw === undefined ? undefined : String(actionRaw)
    const symbolRaw = take('symbol')
    const entry = toNumber(take('entry'))
    const stop = toNumber(take('stop'))
    const target = toNumber(take('target'))
    const quantity = toNumber(take('quantity'))
    const capital = toNumber(take('capital'))

    const confidenceRaw = toNumber(take('confidence'))
    const confidence =
        confidenceRaw === undefined
            ? undefined
            : confidenceRaw <= 1 && confidenceRaw >= 0
              ? confidenceRaw * 100
              : confidenceRaw

    const plan: DecisionPlan = { entry, stop, target }
    if (entry !== undefined && stop !== undefined) plan.risk = Math.abs(entry - stop)
    if (entry !== undefined && target !== undefined) plan.reward = Math.abs(target - entry)
    if (plan.risk !== undefined && plan.reward !== undefined && plan.risk > 0) {
        plan.riskReward = plan.reward / plan.risk
    }
    if (entry !== undefined && target !== undefined) {
        plan.direction = target >= entry ? 'long' : 'short'
    } else if (entry !== undefined && stop !== undefined) {
        plan.direction = stop <= entry ? 'long' : 'short'
    }

    const fields: DecisionField[] = []
    const prose: InterpretedDecision['prose'] = []

    for (const [key, value] of Object.entries(source)) {
        if (consumed.has(key)) continue
        if (typeof value === 'string' && value.length > PROSE_LENGTH) {
            prose.push({ key, label: humanizeKey(key), text: value })
            continue
        }
        if (isScalar(value)) {
            fields.push({ key, label: humanizeKey(key), value: formatScalar(value) })
            continue
        }
        // Nested structures: keep them visible rather than dropping them, but
        // compactly — they are rare and secondary.
        fields.push({ key, label: humanizeKey(key), value: JSON.stringify(value) })
    }

    return {
        action,
        intent: normalizeIntent(action),
        symbol: symbolRaw === null || symbolRaw === undefined ? undefined : String(symbolRaw),
        quantity,
        capital,
        confidence,
        plan,
        fields,
        prose,
        isEmpty: Object.keys(source).length === 0,
    }
}
