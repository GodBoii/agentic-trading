'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useState, type ReactNode } from 'react'
import BrandMark from '@/components/brand-mark'
import { cn } from '@/lib/cn'
import { createClient } from '@/lib/supabase/client'
import { Button } from '@/components/ui/button'

/**
 * The single piece of chrome for the authenticated app.
 *
 * This replaces three divergent headers — the Dashboard's own bar, the AI
 * Trading pill nav ("Amount / Live run / Trades / Dashboard"), and an unused
 * copy of this component — which between them disagreed on section names,
 * ordering, canvas colour and container width.
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
                    className="flex flex-shrink-0 items-center gap-2.5 rounded-lg"
                    aria-label="PolyCognition dashboard"
                >
                    <BrandMark className="h-7 w-7" priority />
                    <span className="hidden text-[13px] font-medium tracking-[-0.02em] text-ink-primary sm:inline">
                        PolyCognition
                    </span>
                </Link>

                <nav
                    className="no-scrollbar -mx-1 flex min-w-0 flex-1 items-center gap-0.5 overflow-x-auto px-1"
                    aria-label="Sections"
                >
                    {NAV_ITEMS.map((item) => {
                        const current = active === item.id
                        return (
                            <Link
                                key={item.id}
                                href={item.href}
                                aria-current={current ? 'page' : undefined}
                                className={cn(
                                    'flex-shrink-0 rounded-lg px-2.5 py-1.5 text-[12px] font-medium tracking-[-0.01em] transition-colors duration-150',
                                    current
                                        ? 'bg-white/[0.06] text-ink-primary'
                                        : 'text-ink-tertiary hover:bg-white/[0.03] hover:text-ink-secondary',
                                )}
                            >
                                {item.label}
                            </Link>
                        )
                    })}
                </nav>

                <div className="flex flex-shrink-0 items-center gap-2">
                    {actions}
                    {email && (
                        <span
                            className="hidden max-w-[180px] truncate border-l border-line pl-3 font-mono text-[10px] text-ink-tertiary lg:inline"
                            title={email}
                        >
                            {email}
                        </span>
                    )}
                    <Button size="sm" onClick={signOut} disabled={signingOut}>
                        {signingOut ? 'Signing out' : 'Sign out'}
                    </Button>
                </div>
            </div>
        </header>
    )
}
