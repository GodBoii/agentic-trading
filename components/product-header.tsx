'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useState, type ReactNode } from 'react'
import BrandMark from '@/components/brand-mark'
import { createClient } from '@/lib/supabase/client'
import { Button } from '@/components/ui/button'
import { SlidingRail } from '@/components/motion/sliding-rail'
import { Tooltip } from '@/components/motion/tooltip'

/**
 * The single piece of chrome for the authenticated app.
 *
 * Sections: Dashboard, Agent, Trades. Longest-prefix matching, so nested agent
 * routes still highlight Agent.
 *
 * Motion. Three changes, each replacing a hard cut:
 *
 *   - The active-section indicator slides (recipe 16) instead of the background
 *     colour jumping from one link to the next. In a three-section app this is
 *     the most-used control on screen, and the travel makes a route change
 *     attributable — you can see which section you left.
 *
 *   - Sign-out swaps its label in place (recipe 04) rather than the text
 *     changing between frames while the request is in flight.
 *
 *   - The truncated email gets a real tooltip (recipe 17) instead of a `title`
 *     attribute. A native `title` has an uncontrollable delay, cannot be
 *     styled, and never appears for keyboard users — which for a truncated
 *     identifier means the full value was effectively unavailable.
 */

const NAV_ITEMS = [
    { id: 'dashboard', label: 'Dashboard', href: '/dashboard' },
    { id: 'agent', label: 'Agent', href: '/dashboard/ai-trading' },
    { id: 'trades', label: 'Trades', href: '/dashboard/trades' },
] as const

export type ProductSection = (typeof NAV_ITEMS)[number]['id']

/** Longest-prefix match, so nested agent routes still highlight Agent. */
function sectionFor(pathname: string): ProductSection {
    if (pathname.startsWith('/dashboard/trades')) return 'trades'
    if (pathname.startsWith('/dashboard/ai-trading')) return 'agent'
    return 'dashboard'
}

export default function ProductHeader({
    email,
    actions,
}: {
    email?: string | null
    /** Section-specific controls, shown at the end of the bar. */
    actions?: ReactNode
}) {
    const pathname = usePathname()
    const router = useRouter()
    const active = sectionFor(pathname || '/dashboard')
    const [signingOut, setSigningOut] = useState(false)

    const signOut = async () => {
        setSigningOut(true)
        try {
            await createClient().auth.signOut()
            router.push('/')
        } finally {
            setSigningOut(false)
        }
    }

    return (
        <header className="sticky top-0 z-40 border-b border-line bg-canvas/90 backdrop-blur-xl">
            <div className="mx-auto flex h-14 max-w-[1280px] items-center gap-3 px-5 sm:gap-5 sm:px-8">
                <Link
                    href="/dashboard"
                    className="group flex flex-shrink-0 items-center gap-2.5 rounded-lg"
                    aria-label="PolyCognition dashboard"
                >
                    <BrandMark
                        className="h-7 w-7 transition-transform duration-[250ms] ease-[cubic-bezier(0.22,1,0.36,1)] group-hover:scale-105"
                        priority
                    />
                    <span className="hidden text-[13px] font-medium tracking-[-0.02em] text-ink-primary sm:inline">
                        PolyCognition
                    </span>
                </Link>

                <div className="no-scrollbar -mx-1 flex min-w-0 flex-1 items-center overflow-x-auto px-1">
                    <SlidingRail activeKey={active} ariaLabel="Sections">
                        {NAV_ITEMS.map((item) => (
                            <Link
                                key={item.id}
                                href={item.href}
                                aria-current={active === item.id ? 'page' : undefined}
                                className="t-tab flex-shrink-0"
                            >
                                {item.label}
                            </Link>
                        ))}
                    </SlidingRail>
                </div>

                <div className="flex flex-shrink-0 items-center gap-2">
                    {actions}
                    {email && (
                        <span className="hidden border-l border-line pl-3 lg:inline">
                            <Tooltip label={email} align="end">
                                <span className="max-w-[180px] truncate font-mono text-[10px] text-ink-tertiary">
                                    {email}
                                </span>
                            </Tooltip>
                        </span>
                    )}
                    <Button size="sm" onClick={signOut} disabled={signingOut} swapLabel>
                        {signingOut ? 'Signing out' : 'Sign out'}
                    </Button>
                </div>
            </div>
        </header>
    )
}
