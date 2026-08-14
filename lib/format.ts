/**
 * Single source of truth for number, currency and time formatting.
 *
 * Formatters are instantiated once at module scope — `Intl.*` constructors are
 * comparatively expensive and these run inside table render loops.
 *
 * Convention:
 *   `money`  — aggregates (balances, invested value, P&L). No paise: at lakh
 *              scale the fraction is noise and it costs two glyphs of column
 *              width on every row.
 *   `price`  — per-unit prices, where paise are material.
 */

const LOCALE = 'en-IN'

const moneyFormat = new Intl.NumberFormat(LOCALE, {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
})

const priceFormat = new Intl.NumberFormat(LOCALE, {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
})

const compactFormat = new Intl.NumberFormat(LOCALE, {
    style: 'currency',
    currency: 'INR',
    notation: 'compact',
    maximumFractionDigits: 1,
})

const countFormat = new Intl.NumberFormat(LOCALE)

const clockFormat = new Intl.DateTimeFormat(LOCALE, { hour: '2-digit', minute: '2-digit' })
const secondsFormat = new Intl.DateTimeFormat(LOCALE, { hour: '2-digit', minute: '2-digit', second: '2-digit' })
const dateTimeFormat = new Intl.DateTimeFormat(LOCALE, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
const weekdayFormat = new Intl.DateTimeFormat(LOCALE, { weekday: 'long' })
const longDateFormat = new Intl.DateTimeFormat(LOCALE, { day: '2-digit', month: 'long', year: 'numeric' })
const headerDateFormat = new Intl.DateTimeFormat(LOCALE, { weekday: 'long', day: 'numeric', month: 'long' })

export const money = (value = 0) => moneyFormat.format(value)
export const price = (value = 0) => priceFormat.format(value)
export const compactMoney = (value = 0) => compactFormat.format(value)
export const count = (value = 0) => countFormat.format(value)

/** Explicit sign, so a positive P&L never reads as a plain number. */
export function signedMoney(value = 0) {
    if (value === 0) return money(0)
    return `${value > 0 ? '+' : '−'}${money(Math.abs(value))}`
}

export function percent(value = 0, digits = 1) {
    return `${value.toFixed(digits)}%`
}

/** P&L direction, for picking a tone. Zero is neutral, not positive. */
export type Direction = 'positive' | 'negative' | 'neutral'

export function directionOf(value?: number | null): Direction {
    if (value === null || value === undefined || !Number.isFinite(value) || value === 0) return 'neutral'
    return value > 0 ? 'positive' : 'negative'
}

/**
 * Broker and agent timestamps arrive in two shapes: ISO-8601 from the agent
 * backend, and `YYYY-MM-DD HH:mm:ss` (no zone, implicitly IST) from Dhan.
 * The space-separated form is not valid ISO and `new Date()` rejects it on
 * some engines, so normalize it to a local-time ISO string first.
 */
export function parseTimestamp(value?: string | number | null): Date | null {
    if (value === null || value === undefined || value === '') return null
    if (typeof value === 'number') {
        // Agent events carry epoch seconds.
        const fromEpoch = new Date(value < 1e12 ? value * 1000 : value)
        return Number.isNaN(fromEpoch.getTime()) ? null : fromEpoch
    }
    const normalized = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(value) ? value.replace(' ', 'T') : value
    const parsed = new Date(normalized)
    return Number.isNaN(parsed.getTime()) ? null : parsed
}

function formatWith(formatter: Intl.DateTimeFormat, value?: string | number | null, fallback = '—') {
    const date = parseTimestamp(value)
    return date ? formatter.format(date) : fallback
}

/** 14:32 */
export const formatClock = (value?: string | number | null, fallback = '—') => formatWith(clockFormat, value, fallback)
/** 14:32:07 — for live event streams where seconds matter. */
export const formatTime = (value?: string | number | null, fallback = '') => formatWith(secondsFormat, value, fallback)
/** 12 Aug, 14:32 */
export const formatDateTime = (value?: string | number | null, fallback = '—') => formatWith(dateTimeFormat, value, fallback)
/** Saturday */
export const formatWeekday = (value?: string | number | null, fallback = 'Unknown') => formatWith(weekdayFormat, value, fallback)
/** 15 August 2026 */
export const formatLongDate = (value?: string | number | null, fallback = 'Date unavailable') => formatWith(longDateFormat, value, fallback)
/** Saturday, 15 August */
export const formatHeaderDate = (value: Date) => headerDateFormat.format(value)

/** Compact elapsed time for "updated 4m ago" affordances. */
export function formatElapsed(value?: string | number | null, now = Date.now()) {
    const date = parseTimestamp(value)
    if (!date) return '—'
    const seconds = Math.round((now - date.getTime()) / 1000)
    if (seconds < 0) return 'just now'
    if (seconds < 45) return 'just now'
    if (seconds < 90) return '1m ago'
    const minutes = Math.round(seconds / 60)
    if (minutes < 60) return `${minutes}m ago`
    const hours = Math.round(minutes / 60)
    if (hours < 24) return `${hours}h ago`
    return `${Math.round(hours / 24)}d ago`
}

/** Wall-clock minutes since midnight — the x-axis for intraday order plots. */
export function minutesSinceMidnight(value?: string | number | null): number | null {
    const date = parseTimestamp(value)
    if (!date) return null
    return date.getHours() * 60 + date.getMinutes() + date.getSeconds() / 60
}

/** Seconds → "1.4s" / "2m 05s", for tool-call durations. */
export function formatDuration(seconds?: number | null) {
    if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return '—'
    if (seconds < 10) return `${seconds.toFixed(2)}s`
    if (seconds < 60) return `${seconds.toFixed(1)}s`
    const minutes = Math.floor(seconds / 60)
    return `${minutes}m ${String(Math.round(seconds % 60)).padStart(2, '0')}s`
}

/** Byte-ish counts for tool payload sizes. */
export function formatCharCount(value?: number | null) {
    if (value === null || value === undefined || !Number.isFinite(value)) return '—'
    if (value < 1000) return `${value} chars`
    if (value < 1_000_000) return `${(value / 1000).toFixed(1)}k chars`
    return `${(value / 1_000_000).toFixed(1)}M chars`
}

/** snake_case / SCREAMING_SNAKE → sentence case, for backend-supplied keys. */
export function humanizeKey(key: string) {
    const spaced = key.replaceAll('_', ' ').trim().toLowerCase()
    return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

export function pluralize(value: number, singular: string, plural = `${singular}s`) {
    return `${count(value)} ${value === 1 ? singular : plural}`
}
