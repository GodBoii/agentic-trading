'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import type { ReactNode } from 'react'
import BrandMark from '@/components/brand-mark'
import { AccountMenu } from '@/components/account/account-menu'
import { SlidingRail } from '@/components/motion/sliding-rail'
import { Agent, History, Portfolio } from '@/components/ui/icons'

/**
 * The single piece of chrome for the authenticated app.
 *
 * Three sections, longest-prefix matched so nested agent routes still highlight
 * Agent. Two changes to what was here before, both about naming things after
 * what they are:
 *
 *   The first section is "Portfolio", not "Dashboard". Its page heading always
 *   said Portfolio, so the nav and the page it opened disagreed — and
 *   "Dashboard" describes a layout rather than content, which makes it useless
 *   next to two siblings that name theirs.
 *
 *   Sign-out and the raw email address have moved into `AccountMenu`. A rare,
 *   mildly destructive action does not belong in the most prominent slot of the
 *   chrome on every screen, and the truncated address was an identifier nobody
 *   could read.
 *
 * Motion. The active-section indicator slides (recipe 16) rather than the
 * background colour jumping from one link to the next. In a three-section app
 * this is the most-used control on screen, and the travel makes a route change
 * attributable — you can see which section you left.
 *
 * The wordmark links to `/`. A logo going home is the strongest convention on
 * the web, and the rail already owns section switching.
 */

const NAV_ITEMS = [
    { id: 'portfolio', label: 'Portfolio', href: '/dashboard', Glyph: Portfolio },
    { id: 'agent', label: 'Agent', href: '/dashboard/ai-trading', Glyph: Agent },
    { id: 'trades', label: 'Trades', href: '/dashboard/trades', Glyph: History },
] as const

export type ProductSection = (typeof NAV_ITEMS)[number]['id']

/** Longest-prefix match, so nested agent routes still highlight Agent. */
function sectionFor(pathname: string): ProductSection {
    if (pathname.startsWith('/dashboard/trades')) return 'trades'
    if (pathname.startsWith('/dashboard/ai-trading')) return 'agent'
    return 'portfolio'
}

export default function ProductHeader({
    email,
    actions,
}: {
    email?: string | null
    /** Section-specific controls, shown before the account menu. */
    actions?: ReactNode
}) {
    const pathname = usePathname()
    const active = sectionFor(pathname || '/dashboard')

    return (
        <header className="sticky top-0 z-[var(--z-header)] border-b border-line bg-canvas/85 backdrop-blur-xl">
            <div className="mx-auto flex h-14 max-w-[1320px] items-center gap-2 px-4 sm:gap-4 sm:px-6 lg:px-8">
                <Link
                    href="/"
                    className="group t-press flex flex-shrink-0 items-center gap-2.5 rounded-lg"
                    aria-label="PolyCognition home"
                >
                    <BrandMark
                        className="h-7 w-7 transition-transform duration-fast ease-smooth group-hover:scale-105"
                        priority
                    />
                    {/* The wordmark is the first thing to go at narrow widths:
                        the mark alone still identifies the product, and the
                        space belongs to the nav. */}
                    <span className="hidden text-[13px] font-medium tracking-[-0.02em] text-ink-primary md:inline">
                        PolyCognition
                    </span>
                </Link>

                {/* The rail can scroll if a future section makes the row too
                    wide, but it is centred rather than left-aligned at desktop
                    widths so the three sections read as the middle of the bar
                    rather than as an appendix to the logo. */}
                <div className="no-scrollbar -mx-1 flex min-w-0 flex-1 items-center overflow-x-auto px-1 sm:justify-center">
                    <SlidingRail activeKey={active} ariaLabel="Sections">
                        {NAV_ITEMS.map(({ id, label, href, Glyph }) => (
                            <Link
                                key={id}
                                href={href}
                                aria-current={active === id ? 'page' : undefined}
                                className="t-tab flex-shrink-0"
                            >
                                {/* Icons appear once there is room for them.
                                    Below `sm` the label alone is unambiguous,
                                    which an icon-only nav would not be. */}
                                <Glyph size={14} className="hidden flex-shrink-0 sm:block" />
                                {label}
                            </Link>
                        ))}
                    </SlidingRail>
                </div>

                <div className="flex flex-shrink-0 items-center gap-2">
                    {actions}
                    <AccountMenu email={email} />
                </div>
            </div>
        </header>
    )
}
