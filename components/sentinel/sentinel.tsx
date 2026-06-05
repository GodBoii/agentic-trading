"use client";

import Nav from "./nav";
import Hero from "./hero";
import AgentNetwork from "./agent-network";
import MarketViz from "./market-viz";
import StrategyStack from "./strategy-stack";
import DecisionEngine from "./decision-engine";
import Trust from "./trust";
import FinalCta from "./final-cta";
import Footer from "./footer";

/**
 * Sentinel — the complete landing page.
 *
 * 7 sections + nav + footer, all orchestrated into a single client
 * component so framer-motion / scroll handlers share a single
 * mounting boundary and we get clean SSR boundaries per section.
 *
 * Sections:
 *   01 Hero             — autonomous intelligence core + live status
 *   02 Agent Network    — 400vh sticky scroll, 4 agents light up
 *   03 Market Viz       — proprietary visual language (rivers / clouds / heatmap)
 *   04 Strategy Stack   — 5 sticky cards
 *   05 Decision Engine  — terminal-style reasoning feed
 *   06 Trust            — massive editorial + 5 metrics
 *   07 Final CTA        — converging particles
 *   Footer              — 25vw SENTINEL + market data streams
 */
export default function Sentinel() {
  return (
    <div className="sentinel-page min-h-screen overflow-x-hidden bg-[#030303] text-[#F8F8F8]">
      <Nav />
      <main>
        <Hero />
        <AgentNetwork />
        <MarketViz />
        <StrategyStack />
        <DecisionEngine />
        <Trust />
        <FinalCta />
      </main>
      <Footer />
    </div>
  );
}
