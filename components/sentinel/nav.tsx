import Link from 'next/link'
import BrandMark from '@/components/brand-mark'
import { PrimaryCta } from './cta'

/**
 * Nav — brand, section links, one auth action.
 *
 * Static bar with a backdrop blur. No scroll-linked motion and no animated
 * indicator: a header that reacts to scrolling competes with the section
 * reveals happening underneath it.
 *
 * Signed in, the bar used to carry a "Dashboard" text link *and* an "Open app"
 * button, both pointing at `/dashboard`. Two controls, same destination, in the
 * same 60px of the page — a visitor has to read both to discover they are the
 * same thing. Signed out the pair is meaningful, because "Sign in" and "Get
 * started" go to different routes and address different people. Signed in there
 * is only one thing left to do, so there is only one control for it.
 *
 * The label matches the hero's ("Open dashboard"). They used to disagree, so the
 * same click target read as two different features depending on where you
 * looked.
 *
 * Motion. One thing moves: the section links draw an underline in from the left
 * over 250ms on hover, so the link acknowledges the pointer. There is no longer
 * a label swap to cover — `signedIn` arrives from the server, so the correct
 * label is in the first paint and the old `key` remount hack is gone.
 */

const LINKS = [
    { label: 'Platform', href: '#platform' },
    { label: 'How it works', href: '#how-it-works' },
]

export default function Nav({ signedIn }: { signedIn: boolean }) {
    return (
        <header className="fixed inset-x-0 top-0 z-[var(--z-nav)] border-b border-white/[0.06] bg-[#030303]/85 backdrop-blur-md">
            <nav className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between px-5 sm:px-8">
                <Link href="/" className="group flex items-center gap-2.5" aria-label="PolyCognition home">
                    <BrandMark
                        className="h-7 w-7 transition-transform duration-[250ms] ease-[cubic-bezier(0.22,1,0.36,1)] group-hover:scale-105"
                        priority
                    />
                    <span className="font-grotesk text-sm font-semibold tracking-[-0.01em] text-white">
                        PolyCognition
                    </span>
                </Link>

                <div className="hidden items-center gap-8 md:flex">
                    {LINKS.map((link) => (
                        <a
                            key={link.label}
                            href={link.href}
                            className="group relative py-1 text-[13px] text-white/55 transition-colors duration-[250ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:text-white"
                        >
                            {link.label}
                            <span
                                aria-hidden
                                className="absolute bottom-0 left-0 h-px w-0 bg-white/40 transition-[width] duration-[250ms] ease-[cubic-bezier(0.22,1,0.36,1)] group-hover:w-full"
                            />
                        </a>
                    ))}
                </div>

                <div className="flex items-center gap-3 sm:gap-5">
                    {signedIn ? (
                        <PrimaryCta href="/dashboard" className="px-4 py-2 text-[13px]">
                            Open dashboard
                        </PrimaryCta>
                    ) : (
                        <>
                            <Link
                                href="/login"
                                className="hidden text-[13px] text-white/55 transition-colors duration-[250ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:text-white sm:inline"
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
