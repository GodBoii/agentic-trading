import Link from 'next/link'
import BrandMark from '@/components/brand-mark'

/**
 * Footer — brand, a one-line description, links that match the session, and the
 * disclaimer.
 *
 * Stays a server component: nothing here has state, `signedIn` arrives as a prop,
 * and the only motion is a colour tween on the links. Making it a client component
 * to add an entrance reveal would ship JavaScript for the least-read part of the
 * page.
 *
 * The links used to be a fixed list of Get started / Sign in / Dashboard shown to
 * everyone. Signed in, the first two invite you to re-create an account you
 * already have. Signed out, "Dashboard" is a trap: `middleware.ts` bounces it
 * straight to `/login`, so the link advertises a destination it cannot deliver.
 * Each state now lists only the routes that work from it, and both keep the
 * section anchors so the footer stays a real navigation block rather than a single
 * orphaned link.
 *
 * Two columns, not four. A four-column link farm is the reflex footer, and with
 * six links total it would have meant columns of one and a half items.
 */

const SECTION_LINKS = [
    { href: '/#platform', label: 'Platform' },
    { href: '/#how-it-works', label: 'How it works' },
]

const SIGNED_IN_LINKS = [
    { href: '/dashboard', label: 'Portfolio' },
    { href: '/dashboard/ai-trading', label: 'Agent' },
]

const SIGNED_OUT_LINKS = [
    { href: '/signup', label: 'Get started' },
    { href: '/login', label: 'Sign in' },
]

export default function Footer({ signedIn }: { signedIn: boolean }) {
    const links = [...SECTION_LINKS, ...(signedIn ? SIGNED_IN_LINKS : SIGNED_OUT_LINKS)]

    return (
        <footer className="border-t border-line px-5 py-14 sm:px-8">
            <div className="mx-auto flex max-w-6xl flex-col gap-10 sm:flex-row sm:items-start sm:justify-between">
                <div className="max-w-sm">
                    <div className="flex items-center gap-2.5">
                        <BrandMark className="h-7 w-7" />
                        <span className="font-display text-[15px] font-medium tracking-[-0.02em]">PolyCognition</span>
                    </div>
                    <p className="mt-3 text-[13px] leading-relaxed text-ink-tertiary">
                        AI trading agents for Indian markets, connected to your Dhan broker.
                    </p>
                </div>

                <nav className="flex flex-wrap gap-x-8 gap-y-3 text-[13px]" aria-label="Footer">
                    {links.map((link) => (
                        <Link
                            key={link.href}
                            href={link.href}
                            className="text-ink-secondary transition-colors duration-fast ease-smooth hover:text-ink-primary"
                        >
                            {link.label}
                        </Link>
                    ))}
                </nav>
            </div>

            <div className="mx-auto mt-12 flex max-w-6xl flex-col gap-3 border-t border-line pt-6 text-[11.5px] text-ink-tertiary sm:flex-row sm:items-center sm:justify-between">
                <span>© 2026 PolyCognition</span>
                <div className="flex gap-5">
                    <Link
                        href="/privacy-policy"
                        className="transition-colors duration-fast ease-smooth hover:text-ink-secondary"
                    >
                        Privacy policy
                    </Link>
                    <Link
                        href="/terms-of-service"
                        className="transition-colors duration-fast ease-smooth hover:text-ink-secondary"
                    >
                        Terms of service
                    </Link>
                </div>
                <span>For research purposes only. Not investment advice.</span>
            </div>
        </footer>
    )
}
