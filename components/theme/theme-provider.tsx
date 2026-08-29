'use client'

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
    DARK_QUERY,
    parseThemeChoice,
    resolveTheme,
    THEME_ATTR,
    THEME_CHOICE_ATTR,
    THEME_READY_ATTR,
    THEME_STORAGE_KEY,
    type ResolvedTheme,
    type ThemeChoice,
} from './theme-bootstrap'

interface ThemeContextValue {
    /** What the user picked. */
    choice: ThemeChoice
    /** What that resolves to now. Use this to branch on appearance. */
    resolved: ResolvedTheme
    setChoice: (next: ThemeChoice) => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

function systemPrefersDark(): boolean {
    if (typeof window === 'undefined') return true
    return window.matchMedia(DARK_QUERY).matches
}

/**
 * Reads the choice the bootstrap script already wrote onto `<html>`.
 *
 * Going to the DOM rather than back to `localStorage` keeps one source of truth
 * for the current render: the script has already validated storage, and if it
 * failed the attribute reflects the fallback it actually applied.
 */
function readChoiceFromDom(): ThemeChoice {
    if (typeof document === 'undefined') return 'system'
    return parseThemeChoice(document.documentElement.getAttribute(THEME_CHOICE_ATTR))
}

/**
 * Owns the appearance state for the whole app.
 *
 * The DOM attributes, not this state, are what the stylesheet reads. That
 * ordering is deliberate: the bootstrap script sets them before React exists,
 * so the provider's job is to keep them in step with later changes rather than
 * to establish them. A provider that owned the initial write would reintroduce
 * the flash the script exists to prevent.
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
    const [choice, setChoiceState] = useState<ThemeChoice>(readChoiceFromDom)
    const [prefersDark, setPrefersDark] = useState<boolean>(systemPrefersDark)

    const resolved = resolveTheme(choice, prefersDark)

    // Follow the OS while the choice is `system`. The listener stays attached
    // for the other two choices as well, so switching back to `system` is
    // already current instead of waiting for the next OS change.
    useEffect(() => {
        const media = window.matchMedia(DARK_QUERY)
        const onChange = (event: MediaQueryListEvent) => setPrefersDark(event.matches)
        media.addEventListener('change', onChange)
        setPrefersDark(media.matches)
        return () => media.removeEventListener('change', onChange)
    }, [])

    // Mirror state onto the element the stylesheet selects on.
    useEffect(() => {
        const root = document.documentElement
        root.setAttribute(THEME_ATTR, resolved)
        root.setAttribute(THEME_CHOICE_ATTR, choice)
    }, [choice, resolved])

    // Enable the colour cross-fade only after the first paint has landed, so
    // the initial render is instant and every later swap is tweened.
    useEffect(() => {
        const frame = window.requestAnimationFrame(() =>
            document.documentElement.setAttribute(THEME_READY_ATTR, 'true'),
        )
        return () => window.cancelAnimationFrame(frame)
    }, [])

    // A second tab changing the theme should not leave this one disagreeing
    // with the value in storage.
    useEffect(() => {
        const onStorage = (event: StorageEvent) => {
            if (event.key !== THEME_STORAGE_KEY) return
            setChoiceState(parseThemeChoice(event.newValue))
        }
        window.addEventListener('storage', onStorage)
        return () => window.removeEventListener('storage', onStorage)
    }, [])

    const setChoice = useCallback((next: ThemeChoice) => {
        setChoiceState(next)
        try {
            window.localStorage.setItem(THEME_STORAGE_KEY, next)
        } catch {
            // Private mode or a full quota. The theme still applies for this
            // session; only the memory of it is lost, which is not worth
            // failing an interaction over.
        }
    }, [])

    const value = useMemo(() => ({ choice, resolved, setChoice }), [choice, resolved, setChoice])

    return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeContextValue {
    const value = useContext(ThemeContext)
    if (!value) throw new Error('useTheme must be used inside ThemeProvider')
    return value
}
