/** Display mirror of the backend's account-capital trade limits. */
export function tradeSlotLimit(accountCapital: number): number {
    if (!Number.isFinite(accountCapital) || accountCapital <= 0) return 0
    if (accountCapital < 2000) return 3
    return accountCapital <= 5000 ? 5 : 10
}

/** @deprecated Compatibility for older bundles. Current UI derives slots from capital. */
export const AUTO_TRADE_SLOTS = 5

/** @deprecated Compatibility for older bundles supplying an explicit slot count. */
export function parseSlotCount(value: unknown): number {
    const slots = Number(value)
    return Number.isInteger(slots) && slots >= 1 && slots <= 20 ? slots : AUTO_TRADE_SLOTS
}

/** Floor each automatic margin allocation to paise. */
export function autoSlotAmount(accountCapital: number, slots = tradeSlotLimit(accountCapital)): number | null {
    if (!Number.isFinite(accountCapital) || accountCapital <= 0) return null
    if (!Number.isInteger(slots) || slots < 1) return null
    const perSlot = Math.floor((accountCapital * 100) / slots) / 100
    return perSlot > 0 ? perSlot : null
}

/** A manual allocation can reduce, but cannot exceed, the account's tier. */
export function fixedSlotCount(accountCapital: number, marginPerTrade: number): number | null {
    if (!Number.isFinite(accountCapital) || accountCapital <= 0) return null
    if (!Number.isFinite(marginPerTrade) || marginPerTrade <= 0) return null
    return Math.min(tradeSlotLimit(accountCapital), Math.floor(accountCapital / marginPerTrade))
}
