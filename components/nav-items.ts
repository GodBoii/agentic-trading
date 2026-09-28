import { Agent, History, Portfolio } from '@/components/ui/icons'

/** The three product sections, shared by the desktop rail and the phone tab bar. */
export const NAV_ITEMS = [
    { id: 'portfolio', label: 'Portfolio', href: '/dashboard', Glyph: Portfolio },
    { id: 'agent', label: 'Agent', href: '/dashboard/ai-trading', Glyph: Agent },
    { id: 'trades', label: 'Trades', href: '/dashboard/trades', Glyph: History },
] as const

export type ProductSection = (typeof NAV_ITEMS)[number]['id']

/** Longest-prefix match, so nested agent routes still highlight Agent. */
export function sectionFor(pathname: string): ProductSection {
    if (pathname.startsWith('/dashboard/trades')) return 'trades'
    if (pathname.startsWith('/dashboard/ai-trading')) return 'agent'
    return 'portfolio'
}
