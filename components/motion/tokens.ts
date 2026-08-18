/**
 * Motion token access from JavaScript.
 *
 * Every recipe that needs orchestration reads its timing back out of CSS
 * rather than hardcoding a matching number in TypeScript. That keeps one
 * source of truth: retuning `--modal-close-dur` in `globals.css` retimes the
 * `setTimeout` that clears the closing class, with no second edit and no
 * chance of the two drifting apart.
 */

/** Read a duration token in milliseconds. Handles both `250ms` and `0.25s`. */
export function motionMs(name: string, fallback: number): number {
    if (typeof window === 'undefined') return fallback
    const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
    if (!raw) return fallback
    const value = parseFloat(raw)
    if (!Number.isFinite(value)) return fallback
    // A bare `s` unit is 1000× a `ms` one; `0.25s` must not become 0.25ms.
    return raw.endsWith('ms') ? value : value * 1000
}

/** Read a unitless or `px` numeric token. */
export function motionNum(name: string, fallback: number): number {
    if (typeof window === 'undefined') return fallback
    const value = parseFloat(getComputedStyle(document.documentElement).getPropertyValue(name))
    return Number.isFinite(value) ? value : fallback
}

/** Read an easing token as a raw CSS timing-function string. */
export function motionEase(name: string, fallback: string): string {
    if (typeof window === 'undefined') return fallback
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}

/**
 * Whether the user has asked for less motion.
 *
 * Checked in JS as well as CSS because the orchestration itself sometimes
 * needs to change, not just the tween: the tilt should not track the pointer
 * at all, and a replay should not schedule timers for animations that will
 * never run.
 */
export function prefersReducedMotion(): boolean {
    if (typeof window === 'undefined' || !window.matchMedia) return false
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/**
 * Force a style recalculation.
 *
 * Required between removing and re-adding an animation class: without a
 * reflow in between, the browser coalesces both mutations into one style
 * pass, sees no change, and the animation never replays. Used by the text
 * swap, number pop-in, success check and error shake.
 */
export function forceReflow(element: HTMLElement | null | undefined): void {
    if (element) void element.offsetWidth
}
