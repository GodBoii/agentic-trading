'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { NAV_ITEMS, sectionFor } from '@/components/nav-items'

/**
 * Section switcher for phones and the installed app.
 *
 * On a phone the three sections were a second row inside the sticky header,
 * which cost about 110px of every screen and put the most-used control at the
 * top edge, the hardest place to reach with a thumb. Here they sit at the
 * bottom, above the home indicator, the way an installed app is expected to
 * behave. Hidden from `md` up, where the header rail takes over.
 */
export function BottomNav() {
    const active = sectionFor(usePathname() || '/dashboard')

    return (
        <nav aria-label="Sections" className="bottom-nav md:hidden">
            <ul className="bottom-nav-list">
                {NAV_ITEMS.map(({ id, label, href, Glyph }) => {
                    const current = active === id
                    return (
                        <li key={id} className="flex-1">
                            <Link
                                href={href}
                                aria-current={current ? 'page' : undefined}
                                className="bottom-nav-link t-press"
                            >
                                <span className="bottom-nav-icon" aria-hidden>
                                    <Glyph size={20} />
                                </span>
                                <span className="bottom-nav-label">{label}</span>
                            </Link>
                        </li>
                    )
                })}
            </ul>
        </nav>
    )
}
