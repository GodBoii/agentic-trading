"use client";

import Nav from "./nav";
import Hero from "./hero";
import AgentNetwork from "./agent-network";
import DecisionEngine from "./decision-engine";
import FinalCta from "./final-cta";
import Footer from "./footer";

/**
 * PolyCognition — landing page.
 *
 * A single, professional page:
 *   Nav           — brand, section links, auth actions
 *   Hero          — what the product is, primary actions
 *   Platform      — the four real services in the stack
 *   How it works  — three-step pipeline
 *   Final CTA     — get started / sign in
 *   Footer        — brand, real links, disclaimer
 */
export default function Sentinel() {
  return (
    <div className="min-h-screen bg-[#030303] text-[#F8F8F8] antialiased">
      <Nav />
      <main>
        <Hero />
        <AgentNetwork />
        <DecisionEngine />
        <FinalCta />
      </main>
      <Footer />
    </div>
  );
}
