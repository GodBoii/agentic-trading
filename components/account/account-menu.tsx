'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'
import { AppearanceControl } from '@/components/theme/appearance-control'
import { Dropdown, useDropdown } from '@/components/motion/dropdown'
import { TextSwap } from '@/components/motion/text-swap'
import { ChevronUpDown, Policy, SignOut } from '@/components/ui/icons'
import { createClient } from '@/lib/supabase/client'
import { cn } from '@/lib/cn'
import { initialsFor, splitAddress } from './identity'

const MENU_ID = 'account-menu'

/**
 * The account surface: who is signed in, how the app should look, the legal
 * pages, and the way out.
 *
 * This replaces a truncated email string sitting next to a permanent "Sign out"
 * button in the header. That arrangement had two problems. Sign-out is a rare
 * and mildly destructive action, and it was the most prominent control in the
 * chrome on every screen — the skill's point about progressive disclosure
 * exactly: common actions stay visible, rare ones move into a menu. And there
 * was nowhere to put anything else, so appearance and the legal links had no
 * home at all.
 *
 * Why a popover and not a settings route: everything in here is one field or
 * one link. A page for that is the same mistake as a page for setting one
 * number, and it would be a route nobody visits twice.
 *
 * Semantics: `role="dialog"`, not `role="menu"`. A menu's keyboard contract is
 * "one active item, arrows move between items", and this surface contains a
 * radio group whose own arrow keys would fight it. A labelled dialog says
 * "composite content" and leaves Tab and the radio group's arrows alone.
 *
 * Motion (recipe 05): the surface grows from the trigger's top-right corner —
 * 250ms open from 0.97, 150ms close to 0.99. The origin is the point: it is
 * what makes the panel read as belonging to the tile that opened it. Sign-out
 * swaps its own label in place (recipe 04) while the request is in flight.
 */
export function AccountMenu({ email }: { email?: string | null }) {
    const { open, setOpen, toggle, anchor } = useDropdown<HTMLDivElement>()
    const router = useRouter()
    const [signingOut, setSigningOut] = useState(false)
    const trigger = useRef<HTMLButtonElement | null>(null)
    const surface = useRef<HTMLDivElement | null>(null)
    /** Only move focus for an open the user caused, never on first mount. */
    const opened = useRef(false)

    const initials = initialsFor(email)
    const { local, domain } = splitAddress(email)

    /**
     * Focus moves into the panel on open and back onto the trigger on close.
     *
     * The panel itself takes focus, not its first control. The first control
     * here would be the appearance radio group — announcing a settings field the
     * moment the menu opens — and the last is sign-out, which should never be
     * where focus lands by default. Focusing the labelled container announces
     * what opened and leaves Tab to do the rest.
     *
     * Without the return-focus branch, dismissing with Escape drops focus onto
     * the document body and a keyboard user restarts from the top of the page.
     */
    useEffect(() => {
        if (open) {
            opened.current = true
            const frame = window.requestAnimationFrame(() => surface.current?.focus())
            return () => window.cancelAnimationFrame(frame)
        }
        if (opened.current) trigger.current?.focus()
    }, [open])

    const signOut = async () => {
        setSigningOut(true)
        try {
            await createClient().auth.signOut()
            router.push('/')
            // `/` renders its auth-dependent copy on the server, so the router
            // cache would hand back the payload from before sign-out and the
            // landing page would still offer "Open dashboard". Refresh discards
            // it and re-renders against the cleared cookie.
            router.refresh()
        } finally {
            setSigningOut(false)
        }
    }

    return (
        <div ref={anchor} className="relative">
            <button
                ref={trigger}
                type="button"
                onClick={toggle}
                aria-haspopup="dialog"
                aria-expanded={open}
                aria-controls={open ? MENU_ID : undefined}
                aria-label={email ? `Account menu for ${email}` : 'Account menu'}
                className={cn(
                    't-press flex items-center gap-1.5 rounded-[11px] border p-1 pr-1.5',
                    'transition-[background-color,border-color] duration-fast ease-smooth',
                    open
                        ? 'border-line-strong bg-surface-strong'
                        : 'border-transparent hover:border-line hover:bg-surface-hover',
                )}
            >
                <span className="identity-tile h-7 w-7 text-[10px]">{initials}</span>
                <ChevronUpDown size={13} className="text-ink-tertiary" />
            </button>

            <Dropdown
                open={open}
                origin="top-right"
                role="dialog"
                ariaLabel="Account"
                id={MENU_ID}
                className="pop-surface absolute right-0 top-[calc(100%+8px)] z-[var(--z-overlay)] w-[272px] p-2"
            >
                <div ref={surface} tabIndex={-1} className="outline-none">
                    {/* Identity. The address wraps at the `@` rather than being
                        truncated: a half-shown address is not an identity, and
                        this is the one place the full value has to be legible. */}
                    <div className="menu-group flex items-center gap-2.5 px-1.5 pb-2.5 pt-1">
                        <span className="identity-tile h-9 w-9 text-[12px]">{initials}</span>
                        <span className="min-w-0">
                            <span className="block text-[9px] uppercase tracking-[0.14em] text-ink-tertiary">
                                Signed in
                            </span>
                            {email ? (
                                <span className="mt-0.5 block break-all font-mono text-[11px] leading-tight text-ink-primary">
                                    {local}
                                    <span className="text-ink-tertiary">{domain}</span>
                                </span>
                            ) : (
                                <span className="mt-0.5 block text-[11px] text-ink-tertiary">
                                    Account details unavailable
                                </span>
                            )}
                        </span>
                    </div>

                    <div className="menu-group px-1.5 py-2">
                        <p
                            id="appearance-label"
                            className="mb-2 text-[9px] uppercase tracking-[0.14em] text-ink-tertiary"
                        >
                            Appearance
                        </p>
                        <AppearanceControl labelledBy="appearance-label" />
                    </div>

                    <nav className="menu-group" aria-label="Policies">
                        <Link href="/privacy-policy" className="menu-row" onClick={() => setOpen(false)}>
                            <Policy size={14} className="text-ink-tertiary" />
                            Privacy policy
                        </Link>
                        <Link href="/terms-of-service" className="menu-row" onClick={() => setOpen(false)}>
                            <Policy size={14} className="text-ink-tertiary" />
                            Terms of service
                        </Link>
                    </nav>

                    <div className="menu-group">
                        <button
                            type="button"
                            data-tone="danger"
                            className="menu-row"
                            onClick={() => void signOut()}
                            disabled={signingOut}
                        >
                            <SignOut size={14} />
                            <TextSwap>{signingOut ? 'Signing out' : 'Sign out'}</TextSwap>
                        </button>
                    </div>
                </div>
            </Dropdown>
        </div>
    )
}
