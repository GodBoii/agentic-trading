import Link from 'next/link'
import BrandMark from '@/components/brand-mark'
import { ThemeMenu } from '@/components/theme/theme-menu'
import { PrimaryCta } from './cta'

/**
 * Nav — brand, section links, appearance, one auth action.
 *
 * Static bar with a backdrop blur. No scroll-linked motion and no animated
 * indicator: a header that reacts to scrolling competes with the section reveals
 * happening underneath it.
 *
 * Signed in, the bar used to carry a "Dashboard" text link *and* an "Open app"
 * button, both pointing at `/dashboard`. Two controls, same destination, within
 * the same 60px of the page — a visitor has to read both to discover they are the
 * same thing. Signed out the pair is meaningful, because "Sign in" and "Get
 * started" go to different routes and address different people. Signed in there
 * is one thing left to do, so there is one control for it.
 *
 * The appearance control lives here rather than only inside the account menu,
 * because a visitor who has not signed in still has to read this page.
 *
 * Motion. One thing moves: the section links draw an underline in from the left
 * over 250ms on hover, so the link acknowledges the pointer. `signedIn` arrives
 * from the server, so the correct label is in the first paint and there is no
 * label swap to cover.
 */

const LINKS = [
    { label: 'Platform', href: '#platform' },
    { label: 'How it works', href: '#how-it-works' },
]

export default function Nav({ signedIn }: { signedIn: boolean }) {
    return (
        <header className="fixed inset-x-0 top-0 z-[var(--z-nav)] border-b border-line bg-[var(--site-canvas)]/85 backdrop-blur-md">
            <a href="#main" className="skip-link">
                Skip to content
            </a>
            <nav className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between gap-4 px-5 sm:px-8">
                <Link href="/" className="group t-press flex items-center gap-2.5" aria-label="PolyCognition home">
                    <BrandMark
                        className="h-7 w-7 transition-transform duration-fast ease-smooth group-hover:scale-105"
                        priority
                    />
                    <span className="font-display text-[15px] font-medium tracking-[-0.02em]">PolyCognition</span>
                </Link>

                <div className="hidden items-center gap-8 md:flex">
                    {LINKS.map((link) => (
                        <a
                            key={link.label}
                            href={link.href}
                            className="group relative py-1 text-[13px] text-ink-secondary transition-colors duration-fast ease-smooth hover:text-ink-primary"
                        >
                            {link.label}
                            <span
                                aria-hidden
                                className="absolute bottom-0 left-0 h-px w-0 bg-line-strong transition-[width] duration-fast ease-smooth group-hover:w-full"
                            />
                        </a>
                    ))}
                </div>

                <div className="flex items-center gap-2 sm:gap-3">
                    <ThemeMenu />
                    {signedIn ? (
                        <PrimaryCta href="/dashboard" className="px-4 py-2 text-[13px]">
                            Open dashboard
                        </PrimaryCta>
                    ) : (
                        <>
                            <Link
                                href="/login"
                                className="hidden px-1 text-[13px] text-ink-secondary transition-colors duration-fast ease-smooth hover:text-ink-primary sm:inline"
                            >
                                Sign in
                            </Link>
                            <PrimaryCta href="/signup" className="px-4 py-2 text-[13px]">
                                Get started
                            </PrimaryCta>
                        </>
                    )}
                </div>
            </nav>
        </header>
    )
}
