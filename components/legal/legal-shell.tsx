import Link from 'next/link'
import type { ReactNode } from 'react'
import BrandMark from '@/components/brand-mark'
import { ThemeMenu } from '@/components/theme/theme-menu'

/**
 * Frame for the privacy policy and the terms.
 *
 * The two pages each carried their own copy of this header, container, prose
 * styling and footer — around three hundred lines of duplicated markup with
 * sixty hardcoded colour values between them, which is exactly how one page ends
 * up on a slightly different grey from the other.
 *
 * Stays a server component. The only interactive things on these pages are links
 * and the appearance button, which brings its own client boundary.
 *
 * The footer cross-links to the sibling document rather than dead-ending: someone
 * reading the terms is one click from the privacy policy, which is the pair of
 * pages people actually navigate between.
 */
export function LegalShell({
    title,
    updated,
    children,
    sibling,
}: {
    title: string
    /** Rendered verbatim. Kept as a string so it cannot drift from the content. */
    updated: string
    children: ReactNode
    sibling: { href: string; label: string }
}) {
    return (
        <div className="flex min-h-[100dvh] flex-col bg-[var(--site-canvas)] text-ink-primary antialiased">
            <header className="border-b border-line px-5 py-4 sm:px-8">
                <div className="mx-auto flex max-w-3xl items-center justify-between gap-4">
                    <Link
                        href="/"
                        className="group t-press flex items-center gap-2.5"
                        aria-label="PolyCognition home"
                    >
                        <BrandMark className="h-7 w-7 transition-transform duration-fast ease-smooth group-hover:scale-105" />
                        <span className="font-display text-[14px] font-medium tracking-[-0.02em]">PolyCognition</span>
                    </Link>
                    <ThemeMenu />
                </div>
            </header>

            <main className="mx-auto w-full max-w-3xl flex-1 px-5 py-14 sm:px-8 sm:py-20">
                <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-ink-tertiary">Legal</p>
                <h1 className="mt-4 font-display text-[30px] font-medium leading-[1.05] tracking-[-0.035em] sm:text-[36px]">
                    {title}
                </h1>
                <p className="mt-3 font-mono text-[11.5px] text-ink-tertiary">Last updated {updated}</p>

                <div className="legal-prose mt-12">{children}</div>
            </main>

            <footer className="border-t border-line px-5 py-7 sm:px-8">
                <div className="mx-auto flex max-w-3xl flex-col gap-2 text-[11.5px] text-ink-tertiary sm:flex-row sm:items-center sm:justify-between">
                    <span>© 2026 PolyCognition</span>
                    <div className="flex gap-5">
                        <Link
                            href={sibling.href}
                            className="transition-colors duration-fast ease-smooth hover:text-ink-secondary"
                        >
                            {sibling.label}
                        </Link>
                        <Link href="/" className="transition-colors duration-fast ease-smooth hover:text-ink-secondary">
                            Home
                        </Link>
                    </div>
                </div>
            </footer>
        </div>
    )
}

/**
 * One numbered clause.
 *
 * `index` is rendered by CSS into the margin at reading widths, so the heading
 * text lines up with the paragraph beneath it instead of being pushed right by
 * its own number. It stays out of the accessible name of the heading, which
 * should read "Data security", not "5. Data security".
 */
export function Clause({ index, heading, children }: { index: number; heading: string; children: ReactNode }) {
    return (
        <section>
            <h2 data-index={String(index).padStart(2, '0')}>{heading}</h2>
            {children}
        </section>
    )
}
