import type { Metadata, Viewport } from 'next'
import { IBM_Plex_Mono, Instrument_Serif, Manrope, Outfit } from 'next/font/google'
import { ThemeProvider } from '@/components/theme/theme-provider'
import { THEME_BOOTSTRAP_SCRIPT } from '@/components/theme/theme-bootstrap'
import './globals.css'

/**
 * Four families, three roles.
 *
 * This replaced seven Google families (Inter, Inter Tight, JetBrains Mono,
 * Space Grotesk, Manrope, IBM Plex Mono, Instrument Serif) where the marketing
 * pages and the product shell used *different* ones for the same roles. Seven
 * families is both a real download cost and the reason the two halves of the
 * site did not look like one product.
 *
 * The CSS variable names describe the role, not the typeface, so a future swap
 * is one line here rather than a search across the stylesheet.
 */
const headline = Outfit({
    subsets: ['latin'],
    variable: '--font-headline',
    weight: ['400', '500', '600'],
    display: 'swap',
})

const body = Manrope({
    subsets: ['latin'],
    variable: '--font-body',
    weight: ['400', '500', '600', '700'],
    display: 'swap',
})

/** Every figure in the product. Tabular widths and a slashed zero. */
const numeric = IBM_Plex_Mono({
    subsets: ['latin'],
    variable: '--font-numeric',
    weight: ['400', '500', '600'],
    display: 'swap',
})

/** One editorial italic, on the marketing surface only. */
const editorial = Instrument_Serif({
    subsets: ['latin'],
    variable: '--font-editorial',
    weight: ['400'],
    style: ['normal', 'italic'],
    display: 'swap',
})

export const metadata: Metadata = {
    title: {
        default: 'PolyCognition — AI trading agents for Indian markets',
        template: '%s · PolyCognition',
    },
    description:
        'Connect your Dhan broker and let AI agents scan the NSE universe, surface intraday opportunities, and execute within your risk limits.',
    applicationName: 'PolyCognition',
    icons: {
        icon: '/icon.png',
        apple: '/icon.png',
    },
    openGraph: {
        title: 'PolyCognition — AI trading agents for Indian markets',
        description:
            'Scan the NSE universe, read the reasoning behind every signal, and keep execution inside limits you set.',
        siteName: 'PolyCognition',
        type: 'website',
    },
    formatDetection: {
        telephone: false,
    },
}

export const viewport: Viewport = {
    width: 'device-width',
    initialScale: 1,
    /**
     * Matches each theme's canvas, so the browser chrome on a phone does not
     * sit as a black band above a paper-coloured page.
     */
    themeColor: [
        { media: '(prefers-color-scheme: dark)', color: '#0C0B0A' },
        { media: '(prefers-color-scheme: light)', color: '#F1EDE6' },
    ],
}

export default function RootLayout({
    children,
}: Readonly<{
    children: React.ReactNode
}>) {
    return (
        /**
         * `data-theme` is written by the bootstrap script below before first
         * paint, so the server markup deliberately carries no theme attribute.
         * `suppressHydrationWarning` covers exactly that: React would otherwise
         * report the attribute the script added as a mismatch.
         */
        <html lang="en" suppressHydrationWarning>
            <head>
                {/*
                 * Inline and blocking, on purpose. Resolving the theme in an
                 * effect means the first paint uses the stylesheet default and
                 * then flips — a white flash on every cold load for anyone on
                 * the dark theme, which is the majority here.
                 */}
                <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP_SCRIPT }} />
            </head>
            <body
                className={`${headline.variable} ${body.variable} ${numeric.variable} ${editorial.variable} font-sans antialiased bg-canvas text-ink-primary`}
            >
                <ThemeProvider>{children}</ThemeProvider>
            </body>
        </html>
    )
}
