import Nav from './nav'
import Hero from './hero'
import AgentNetwork from './agent-network'
import DecisionEngine from './decision-engine'
import FinalCta from './final-cta'
import Footer from './footer'

/**
 * PolyCognition — landing page.
 *
 *   Nav           brand, section links, appearance, one auth action
 *   Hero          what the product is, primary action
 *   Platform      the four real services in the stack
 *   How it works  the three-step pipeline
 *   Final CTA     sign up, or open the app if already signed in
 *   Footer        brand, links that match the current session, disclaimer
 *
 * `signedIn` is resolved on the server by `app/page.tsx` and threaded down as a
 * prop. Four sections need it; none of them should be fetching it. This file
 * dropped its `'use client'` directive along with the auth effects it used to
 * host, so the nav and footer stay server-rendered — the only client JavaScript
 * either one pulls in is the appearance button.
 *
 * The surface reads from `--site-canvas` rather than a literal `#030303`, so the
 * marketing pages follow the same theme as the product. They are a shade off the
 * product canvas on purpose: a different room, not a different palette.
 *
 * `overflow-x-hidden` is load-bearing. Several sections carry offscreen ambient
 * geometry, and without it a phone gets a horizontal scrollbar for a gradient
 * nobody can see.
 */
export default function Sentinel({ signedIn }: { signedIn: boolean }) {
    return (
        <div className="grain w-full max-w-full overflow-x-hidden bg-[var(--site-canvas)] text-ink-primary antialiased">
            <Nav signedIn={signedIn} />
            <main id="main">
                <Hero signedIn={signedIn} />
                <AgentNetwork />
                <DecisionEngine />
                <FinalCta signedIn={signedIn} />
            </main>
            <Footer signedIn={signedIn} />
        </div>
    )
}
