import Nav from './nav'
import Hero from './hero'
import AgentNetwork from './agent-network'
import DecisionEngine from './decision-engine'
import FinalCta from './final-cta'
import Footer from './footer'

/**
 * PolyCognition — landing page.
 *
 *   Nav           — brand, section links, one auth action
 *   Hero          — what the product is, primary action
 *   Platform      — the four real services in the stack
 *   How it works  — three-step pipeline
 *   Final CTA     — sign up, or open the app if already signed in
 *   Footer        — brand, links that match the current session, disclaimer
 *
 * `signedIn` is resolved on the server by `app/page.tsx` and threaded down as a
 * prop. Four sections need it; none of them should be fetching it. This file
 * dropped its `'use client'` directive along with the auth effects it used to
 * host, so the nav and footer now ship no JavaScript at all.
 */
export default function Sentinel({ signedIn }: { signedIn: boolean }) {
    return (
        <div className="min-h-screen bg-[#030303] text-[#F8F8F8] antialiased">
            <Nav signedIn={signedIn} />
            <main>
                <Hero signedIn={signedIn} />
                <AgentNetwork />
                <DecisionEngine />
                <FinalCta signedIn={signedIn} />
            </main>
            <Footer signedIn={signedIn} />
        </div>
    )
}
