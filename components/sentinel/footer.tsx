import Link from 'next/link'
import BrandMark from '@/components/brand-mark'

/**
 * Footer — brand, a one-line description, links that match the session, and the
 * disclaimer.
 *
 * Stays a server component: nothing here has state, `signedIn` arrives as a
 * prop, and the only motion is a colour tween on the links. Making it a client
 * component to add an entrance reveal would ship JavaScript for the least-read
 * part of the page.
 *
 * The links used to be a fixed list of Get started / Sign in / Dashboard shown
 * to everyone. Signed in, the first two invite you to re-create an account you
 * already have. Signed out, "Dashboard" is a trap: `middleware.ts` bounces it
 * straight to `/login`, so the link advertises a destination it cannot deliver.
 * Each state now lists only the routes that work from it, and both keep the two
 * section anchors so the footer stays a real navigation block rather than a
 * single orphaned link.
 *
 * The hover is tokenised (250ms on the house curve) so it matches the nav.
 */

const SECTION_LINKS = [
    { href: '/#platform', label: 'Platform' },
    { href: '/#how-it-works', label: 'How it works' },
]

const SIGNED_IN_LINKS = [{ href: '/dashboard', label: 'Dashboard' }]

const SIGNED_OUT_LINKS = [
    { href: '/signup', label: 'Get started' },
    { href: '/login', label: 'Sign in' },
]

export default function Footer({ signedIn }: { signedIn: boolean }) {
    const links = [...SECTION_LINKS, ...(signedIn ? SIGNED_IN_LINKS : SIGNED_OUT_LINKS)]

    return (
        <footer className="border-t border-white/[0.05] bg-[#030303] px-5 py-12 sm:px-8">
            <div className="mx-auto flex max-w-6xl flex-col gap-8 sm:flex-row sm:items-start sm:justify-between">
                <div className="max-w-sm">
                    <div className="flex items-center gap-2.5">
                        <BrandMark className="h-7 w-7" />
                        <span className="font-grotesk text-sm font-semibold text-white">PolyCognition</span>
                    </div>
                    <p className="mt-3 text-[13px] leading-relaxed text-white/40">
                        AI trading agents for Indian markets, connected to your Dhan broker.
                    </p>
                </div>

                <nav className="flex flex-wrap gap-x-6 gap-y-3 text-[13px]" aria-label="Footer">
                    {links.map((link) => (
                        <Link
                            key={link.href}
                            href={link.href}
                            className="text-white/45 transition-colors duration-[250ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:text-white"
                        >
                            {link.label}
                        </Link>
                    ))}
                </nav>
            </div>

            <div className="mx-auto mt-10 flex max-w-6xl flex-col gap-2 border-t border-white/[0.05] pt-6 sm:flex-row sm:items-center sm:justify-between">
                <span className="text-[12px] text-white/30">© 2026 PolyCognition</span>
                <div className="flex gap-4 text-[12px]">
                    <Link
                        href="/privacy-policy"
                        className="text-white/30 transition-colors duration-[250ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:text-white/60"
                    >
                        Privacy Policy
                    </Link>
                    <Link
                        href="/terms-of-service"
                        className="text-white/30 transition-colors duration-[250ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:text-white/60"
                    >
                        Terms of Service
                    </Link>
                </div>
                <span className="text-[12px] text-white/30">
                    For research purposes only · Not investment advice
                </span>
            </div>
        </footer>
    )
}
