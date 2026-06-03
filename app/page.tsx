import Nav from "@/components/landing/nav";
import Hero from "@/components/landing/hero";
import OperatingSystem from "@/components/landing/operating-system";
import Capabilities from "@/components/landing/capabilities";
import Strategies from "@/components/landing/strategies";
import Trust from "@/components/landing/trust";
import Performance from "@/components/landing/performance";
import Proof from "@/components/landing/proof";
import FinalCTA from "@/components/landing/final-cta";

export const metadata = {
  title: "Aetheria — Autonomous AI Trading Intelligence",
  description:
    "Deploy autonomous AI agents that analyze markets, execute strategies, manage risk, and optimize capital around the clock. The future trades itself.",
};

export default function HomePage() {
  return (
    <div className="relative min-h-screen bg-[#050505] text-white overflow-x-hidden">
      <Nav />
      <main>
        <Hero />
        <OperatingSystem />
        <Capabilities />
        <Strategies />
        <Trust />
        <Performance />
        <Proof />
        <FinalCTA />
      </main>
    </div>
  );
}
