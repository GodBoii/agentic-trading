'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import type { ReactNode } from 'react'
import BrandMark from '@/components/brand-mark'
import { AccountMenu } from '@/components/account/account-menu'
import { SlidingRail } from '@/components/motion/sliding-rail'
import { PwaControls } from '@/components/pwa-controls'
import { NAV_ITEMS, sectionFor } from '@/components/nav-items'

export type { ProductSection } from '@/components/nav-items'

/**
 * Chrome for the authenticated app.
 *
 * From `md` up the three sections sit in the header as a sliding rail. Below
 * that the header is one short row (brand, install, account) and the sections
 * move to `BottomNav`. The header pads for the top safe area so the installed
 * app does not draw under the status bar or a notch.
 */
export default function ProductHeader({
    email,
    actions,
}: {
    email?: string | null
    /** Section-specific controls, shown before the account menu. */
    actions?: ReactNode
}) {
    const active = sectionFor(usePathname() || '/dashboard')

    return (
        <header className="product-header chrome-glass sticky top-0 z-[var(--z-header)] border-b border-line">
            <div className="product-header-inner mx-auto flex h-14 max-w-[1320px] items-center gap-3 px-4 sm:gap-4 sm:px-6 lg:px-8">
                <Link href="/" className="t-press flex min-w-0 flex-shrink-0 items-center gap-2.5 rounded-lg" aria-label="PolyCognition home">
                    <BrandMark className="h-7 w-7 flex-shrink-0" priority />
                    <span className="text-[15px] font-medium tracking-[-0.02em] text-ink-primary md:max-lg:hidden">
                        PolyCognition
                    </span>
                </Link>

                <div className="hidden min-w-0 flex-1 justify-center md:flex">
                    <SlidingRail activeKey={active} ariaLabel="Sections">
                        {NAV_ITEMS.map(({ id, label, href, Glyph }) => (
                            <Link
                                key={id}
                                href={href}
                                aria-current={active === id ? 'page' : undefined}
                                className="t-tab flex-shrink-0"
                            >
                                <Glyph size={14} className="flex-shrink-0" />
                                {label}
                            </Link>
                        ))}
                    </SlidingRail>
                </div>

                <div className="ml-auto flex flex-shrink-0 items-center gap-2 md:ml-0">
                    {actions}
                    <PwaControls />
                    <AccountMenu email={email} />
                </div>
            </div>
        </header>
    )
}
