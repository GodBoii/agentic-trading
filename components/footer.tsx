import React from "react";
import Link from "next/link";
import LiveTicker from "./landing/live-ticker";

export default function Footer() {
  return (
    <footer className="relative w-full bg-[#050505] border-t border-line overflow-hidden">
      {/* Subtle live ticker at the very top of footer */}
      <LiveTicker />

      {/* Large editorial typography */}
      <div className="relative px-6 lg:px-8 pt-24 pb-10">
        <div className="mx-auto max-w-7xl">
          <div className="font-display text-[18vw] lg:text-[16vw] leading-[0.85] tracking-[-0.05em] text-white/[0.06] select-none pointer-events-none -mb-8">
            AETHERIA
          </div>
        </div>
      </div>

      <div className="relative mx-auto max-w-7xl px-6 lg:px-8 pb-12">
        <div className="grid grid-cols-1 md:grid-cols-12 gap-10">
          {/* Brand */}
          <div className="md:col-span-5 flex flex-col gap-4">
            <div className="flex items-center gap-2.5">
              <div className="relative h-7 w-7">
                <div className="absolute inset-0 rounded-full bg-gradient-to-br from-accent to-success opacity-80 blur-md" />
                <div className="absolute inset-[3px] rounded-full bg-[#0a0a0c] flex items-center justify-center">
                  <div className="h-1.5 w-1.5 rounded-full bg-white" />
                </div>
              </div>
              <span className="text-[15px] font-medium tracking-[-0.02em] text-white">
                Aetheria
              </span>
            </div>
            <p className="text-[14px] text-ink-secondary leading-relaxed max-w-sm">
              Autonomous AI trading intelligence. Engineered for precision,
              audited for trust, designed for the next generation of markets.
            </p>
            <div className="flex items-center gap-2 mt-2">
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full rounded-full bg-success opacity-60 animate-pulse-ring" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-success" />
              </span>
              <span className="text-[11px] font-mono uppercase tracking-[0.18em] text-success">
                System online
              </span>
            </div>
          </div>

          {/* Product */}
          <div className="md:col-span-2 flex flex-col gap-3">
            <h3 className="text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary mb-1">
              Product
            </h3>
            <Link href="#system" className="text-[13px] text-ink-secondary hover:text-white transition-colors">
              Operating System
            </Link>
            <Link href="#agents" className="text-[13px] text-ink-secondary hover:text-white transition-colors">
              Agents
            </Link>
            <Link href="#strategies" className="text-[13px] text-ink-secondary hover:text-white transition-colors">
              Strategies
            </Link>
            <Link href="#performance" className="text-[13px] text-ink-secondary hover:text-white transition-colors">
              Performance
            </Link>
          </div>

          {/* Company */}
          <div className="md:col-span-2 flex flex-col gap-3">
            <h3 className="text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary mb-1">
              Company
            </h3>
            <Link href="https://aetheriaai.online" target="_blank" className="text-[13px] text-ink-secondary hover:text-white transition-colors">
              About
            </Link>
            <Link href="mailto:aetheriaai1@gmail.com" className="text-[13px] text-ink-secondary hover:text-white transition-colors">
              Contact
            </Link>
            <Link href="https://github.com/GodBoii" target="_blank" className="text-[13px] text-ink-secondary hover:text-white transition-colors">
              GitHub
            </Link>
          </div>

          {/* Legal */}
          <div className="md:col-span-3 flex flex-col gap-3">
            <h3 className="text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary mb-1">
              Legal
            </h3>
            <span className="text-[13px] text-ink-secondary">
              Architect:{" "}
              <span className="text-white">Prajwal Ghadge</span>
            </span>
            <span className="text-[13px] text-ink-secondary">
              SOC 2 Type II · AES-256
            </span>
            <span className="text-[13px] text-ink-tertiary text-[11px] font-mono uppercase tracking-[0.18em]">
              Terminal ID: AETH-001
            </span>
          </div>
        </div>

        {/* Bottom bar */}
        <div className="mt-16 pt-6 border-t border-line flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
          <p className="text-[11px] font-mono uppercase tracking-[0.18em] text-ink-tertiary">
            © {new Date().getFullYear()} Aetheria AI · All systems operational
          </p>
          <p className="text-[11px] font-mono uppercase tracking-[0.18em] text-ink-tertiary">
            Built for the next generation of markets
          </p>
        </div>
      </div>
    </footer>
  );
}
