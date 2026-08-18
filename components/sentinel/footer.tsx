import Link from 'next/link'
import BrandMark from '@/components/brand-mark'

/**
 * Footer — brand, a one-line description, real links, and the disclaimer.
 *
 * Stays a server component: nothing here has state, and the only motion is a
 * colour tween on the links. Making it a client component to add an entrance
 * reveal would ship JavaScript for the least-read part of the page.
 *
 * The link hover is tokenised (250ms on the house curve) so it matches the nav
 * rather than using its own 300ms as it did before.
 */

const LINKS = [
    { href: '/signup', label: 'Get started' },
    { href: '/login', label: 'Sign in' },
    { href: '/dashboard', label: 'Dashboard' },
]

export default function Footer() {
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

                <nav className="flex gap-6 text-[13px]" aria-label="Footer">
                    {LINKS.map((link) => (
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
                <span className="text-[12px] text-white/30">
                    For research purposes only · Not investment advice
                </span>
            </div>
        </footer>
    )
}
