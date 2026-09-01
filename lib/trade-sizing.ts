/**
 * Automatic trade sizing rule.
 *
 * Auto mode divides the available broker balance into equal slots instead of
 * committing the whole balance to the first event that clears the scanner. One
 * slot per concurrent trade, so a position taken at 09:20 does not starve the
 * later trades that the agent may want during the session.
 *
 * The slot count is a product rule, not a display detail, so it lives here
 * rather than inside the panel that renders it. The backend owns the figure at
 * execution time; when `/api/ai-trading/config` starts returning `auto_slots`
 * the UI reads that and falls back to this constant.
 */

/** Concurrent trades auto mode budgets for. */
export const AUTO_TRADE_SLOTS = 5

/**
 * Rupees one auto-mode trade may use.
 *
 * Floored to paise: the figure is a cap, and rounding a cap up would
 * let a slot ask for money the account does not have. Returns `null` when the
 * balance cannot fund a slot, so callers must handle "no slot available"
 * rather than render a misleading zero.
 */
export function autoSlotAmount(availableBalance: number, slots: number = AUTO_TRADE_SLOTS): number | null {
    if (!Number.isFinite(availableBalance) || availableBalance <= 0) return null
    if (!Number.isInteger(slots) || slots < 1) return null
    const perSlot = Math.floor((availableBalance * 100) / slots) / 100
    return perSlot > 0 ? perSlot : null
}

/** Guards a slot count arriving from the API before it reaches the UI. */
export function parseSlotCount(value: unknown): number {
    const slots = Number(value)
    return Number.isInteger(slots) && slots >= 1 && slots <= 20 ? slots : AUTO_TRADE_SLOTS
}

/** Concurrent Fixed-mode trades supported by the current account margin. */
export function fixedSlotCount(availableBalance: number, marginPerTrade: number): number | null {
    if (!Number.isFinite(availableBalance) || availableBalance <= 0) return null
    if (!Number.isFinite(marginPerTrade) || marginPerTrade <= 0) return null
    return Math.floor(availableBalance / marginPerTrade)
}
