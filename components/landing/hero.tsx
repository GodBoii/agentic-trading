"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import AICore from "./ai-core";
import ParticleField from "./particle-field";
import LiveTicker from "./live-ticker";

const ease = [0.16, 1, 0.3, 1] as const;

const METRICS = [
  { label: "Alpha Generated", value: "+24.8%", accent: "text-success" },
  { label: "Execution Accuracy", value: "97.6%", accent: "text-white" },
  { label: "Simulated Volume", value: "$1.2B", accent: "text-white" },
  { label: "Autonomous Runtime", value: "24/7", accent: "text-accent" },
];

export default function Hero() {
  return (
    <section className="relative min-h-screen w-full overflow-hidden bg-grid-fine bg-spotlight">
      {/* Particle field */}
      <div className="absolute inset-0 opacity-70">
        <ParticleField />
      </div>

      {/* Radial vignette overlay — top + bottom fades for content legibility */}
      <div className="absolute inset-x-0 top-0 h-40 bg-gradient-to-b from-[#050505] to-transparent pointer-events-none" />
      <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-[#050505] to-transparent pointer-events-none" />

      <div className="relative z-10 mx-auto max-w-7xl px-6 lg:px-8 pt-36 sm:pt-44 pb-24">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 lg:gap-8 items-center">
          {/* ── LEFT: Editorial copy ── */}
          <div className="lg:col-span-7 flex flex-col">
            {/* Eyebrow */}
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, ease, delay: 0.2 }}
              className="inline-flex items-center gap-2 self-start"
            >
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full rounded-full bg-success opacity-60 animate-pulse-ring" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-success" />
              </span>
              <span className="text-[11px] font-mono uppercase tracking-[0.22em] text-white/60">
                Autonomous Intelligence · Live
              </span>
            </motion.div>

            {/* Headline */}
            <motion.h1
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 1, ease, delay: 0.3 }}
              className="mt-8 font-display text-display-xl text-white"
            >
              The future{" "}
              <span className="font-serif-italic text-white/90">trades</span>
              <br />
              itself.
            </motion.h1>

            {/* Subhead */}
            <motion.p
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.9, ease, delay: 0.5 }}
              className="mt-8 max-w-xl text-[17px] leading-[1.55] text-ink-secondary text-pretty"
            >
              Deploy autonomous AI agents that analyze markets, execute
              strategies, manage risk, and optimize capital around the clock —
              with institutional precision.
            </motion.p>

            {/* CTAs */}
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.9, ease, delay: 0.65 }}
              className="mt-10 flex flex-col sm:flex-row gap-3"
            >
              <Link
                href="/signup"
                className="group relative inline-flex items-center justify-center gap-2 rounded-full bg-white px-6 py-3.5 text-[14px] font-medium text-black transition-all duration-500 ease-out-expo hover:shadow-[0_0_32px_rgba(255,255,255,0.18)] hover:-translate-y-0.5"
              >
                <span>Launch Agent</span>
                <span className="inline-block transition-transform duration-300 group-hover:translate-x-0.5">
                  →
                </span>
              </Link>
              <button
                type="button"
                className="group inline-flex items-center justify-center gap-2 rounded-full border border-white/15 bg-white/[0.04] backdrop-blur-sm px-6 py-3.5 text-[14px] font-medium text-white transition-all duration-500 ease-out-expo hover:bg-white/[0.08] hover:border-white/25"
              >
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full rounded-full bg-accent opacity-60 animate-pulse-ring" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-accent" />
                </span>
                <span>Watch Live Demo</span>
              </button>
            </motion.div>

            {/* Metrics strip */}
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.9, ease, delay: 0.85 }}
              className="mt-16 grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-6 border-t border-line pt-8"
            >
              {METRICS.map((m) => (
                <div key={m.label} className="flex flex-col gap-1.5">
                  <span
                    className={`nums text-[26px] sm:text-[28px] font-medium tracking-tight leading-none ${m.accent}`}
                  >
                    {m.value}
                  </span>
                  <span className="text-[11px] font-mono uppercase tracking-[0.18em] text-ink-tertiary">
                    {m.label}
                  </span>
                </div>
              ))}
            </motion.div>
          </div>

          {/* ── RIGHT: AI Core ── */}
          <motion.div
            initial={{ opacity: 0, scale: 0.94 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 1.4, ease, delay: 0.4 }}
            className="lg:col-span-5 relative"
          >
            <div className="relative">
              <AICore />

              {/* Floating data cards — institutional feel */}
              <motion.div
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.8, ease, delay: 1.1 }}
                className="absolute top-[18%] -left-2 sm:-left-8 glass rounded-lg px-3.5 py-2.5 hidden sm:block"
              >
                <div className="flex items-center gap-2.5">
                  <div className="h-1.5 w-1.5 rounded-full bg-success animate-pulse-soft" />
                  <div className="flex flex-col gap-0.5">
                    <span className="text-[9px] font-mono uppercase tracking-[0.18em] text-ink-tertiary">
                      Strategy
                    </span>
                    <span className="text-[12px] font-medium text-white nums">
                      +14.2% · 30D
                    </span>
                  </div>
                </div>
              </motion.div>

              <motion.div
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.8, ease, delay: 1.3 }}
                className="absolute bottom-[22%] -right-2 sm:-right-8 glass rounded-lg px-3.5 py-2.5 hidden sm:block"
              >
                <div className="flex items-center gap-2.5">
                  <div className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse-soft" />
                  <div className="flex flex-col gap-0.5">
                    <span className="text-[9px] font-mono uppercase tracking-[0.18em] text-ink-tertiary">
                      Latency
                    </span>
                    <span className="text-[12px] font-medium text-white nums">
                      38ms avg
                    </span>
                  </div>
                </div>
              </motion.div>
            </div>
          </motion.div>
        </div>
      </div>

      {/* Live ticker at bottom of hero */}
      <div className="relative z-10">
        <LiveTicker />
      </div>
    </section>
  );
}
