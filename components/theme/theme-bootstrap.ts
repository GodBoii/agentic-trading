/**
 * Theme constants plus the script that resolves the theme before first paint.
 *
 * Deliberately a plain module with no `'use client'` and no React import: the
 * root layout is a server component and needs the script string at render time,
 * while the provider and the appearance control need the same key and the same
 * parser. One definition, three consumers.
 */

/** What the user chose. `system` is a real choice, not the absence of one. */
export type ThemeChoice = 'system' | 'light' | 'dark'

/** What that choice resolves to right now. Only ever these two. */
export type ResolvedTheme = 'light' | 'dark'

export const THEME_STORAGE_KEY = 'polycognition.appearance'

/** Carries the raw choice, so `system` survives a reload as `system`. */
export const THEME_CHOICE_ATTR = 'data-theme-choice'

/** Carries the resolved theme. This is what `globals.css` selects on. */
export const THEME_ATTR = 'data-theme'

/**
 * Set once the first paint is done, so the colour cross-fade in `globals.css`
 * applies to user-initiated swaps but not to the initial render.
 */
export const THEME_READY_ATTR = 'data-theme-ready'

export const DARK_QUERY = '(prefers-color-scheme: dark)'

/**
 * Anything else in storage is treated as "no preference recorded" rather than
 * trusted. `localStorage` is user-writable and shared with every script on the
 * origin, so its contents are untrusted input like any other boundary.
 */
export function parseThemeChoice(value: unknown): ThemeChoice {
    return value === 'light' || value === 'dark' || value === 'system' ? value : 'system'
}

export function resolveTheme(choice: ThemeChoice, systemPrefersDark: boolean): ResolvedTheme {
    if (choice === 'system') return systemPrefersDark ? 'dark' : 'light'
    return choice
}

/**
 * Runs inline in `<head>`, before the stylesheet paints.
 *
 * It has to be blocking. Resolving the theme in an effect means the first frame
 * uses whatever the stylesheet defaults to and then flips, which is a full-page
 * flash on every cold load for anyone not on that default.
 *
 * Written as a string rather than a bundled module for the same reason: a
 * module would be fetched and executed after the first paint.
 *
 * Kept minimal and total — a throw here would leave the page unstyled, so the
 * catch falls back to dark rather than to nothing.
 */
export const THEME_BOOTSTRAP_SCRIPT = `(function(){try{var k=${JSON.stringify(
    THEME_STORAGE_KEY,
)},s=localStorage.getItem(k),c=(s==="light"||s==="dark"||s==="system")?s:"system",d=c==="dark"||(c==="system"&&window.matchMedia(${JSON.stringify(
    DARK_QUERY,
)}).matches),r=document.documentElement;r.setAttribute(${JSON.stringify(
    THEME_ATTR,
)},d?"dark":"light");r.setAttribute(${JSON.stringify(
    THEME_CHOICE_ATTR,
)},c);}catch(e){document.documentElement.setAttribute(${JSON.stringify(THEME_ATTR)},"dark");}})();`
