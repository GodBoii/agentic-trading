"use client";

import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import IntelligenceCore from "./intelligence-core";

/**
 * Hero — Section 1.
 *
 * Layout (desktop):
 *   left:   eyebrow, 4-line headline, subtitle, CTAs
 *   right:  glass status card (sticky-positioned absolute)
 *   behind: the IntelligenceCore (full-bleed)
 *
 * Mobile:
 *   the core shrinks and moves behind the headline, the status card drops
 *   below the CTAs as a horizontal strip.
 */

const spring = { type: "spring", stiffness: 120, damping: 20, bounce: 0 } as const;

const SPRING = { type: "spring" as const, stiffness: 120, damping: 20, bounce: 0 };

function StatusCard() {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((v) => v + 1), 2400);
    return () => clearInterval(id);
  }, []);

  const rows: [string, string][] = [
    ["Market State",        "ACTIVE"],
    ["Signals Processed",   (18437229 + tick * 58231).toLocaleString("en-US")],
    ["Agent Decisions",     (4281 + tick * 17).toLocaleString("en-US")],
    ["Execution Accuracy",  `${(97.8 + (tick % 4) * 0.03).toFixed(1)}%`],
  ];

  return (
    <motion.aside
      initial={{ opacity: 0, x: 30 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ ...SPRING, delay: 0.35 }}
      className="glass-liquid hidden w-[330px] p-5 lg:flex lg:flex-col"
      aria-label="Live system status"
    >
      <div className="mb-5 flex items-center justify-between">
        <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/45">
          Live system status
        </span>
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full rounded-full bg-[#00FF9D] opacity-60 animate-pulse-ring" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-[#00FF9D]" />
        </span>
      </div>

      <div className="space-y-3.5">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-end justify-between border-b border-white/[0.06] pb-3">
            <span className="text-[12px] text-white/55">{label}</span>
            <motion.span
              key={`${label}-${value}`}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
              className="nums font-mono text-[12px] text-[#F8F8F8]"
            >
              {value}
            </motion.span>
          </div>
        ))}
      </div>

      <div className="mt-5 flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.18em] text-white/30">
        <span>Uptime 99.99%</span>
        <span>Latency 12ms</span>
      </div>
    </motion.aside>
  );
}

function StatusStripMobile() {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((v) => v + 1), 2400);
    return () => clearInterval(id);
  }, []);

  const items: { label: string; value: string; tone: "neutral" | "profit" }[] = [
    { label: "Market",     value: "ACTIVE",                      tone: "neutral" },
    { label: "Signals",    value: (18437229 + tick * 58231).toLocaleString("en-US"), tone: "neutral" },
    { label: "Decisions",  value: (4281 + tick * 17).toLocaleString("en-US"),      tone: "neutral" },
    { label: "Accuracy",   value: `${(97.8 + (tick % 4) * 0.03).toFixed(1)}%`,      tone: "profit" },
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...SPRING, delay: 0.4 }}
      className="glass-card mt-8 grid grid-cols-4 gap-px overflow-hidden p-3 sm:hidden"
    >
      {items.map((item) => (
        <div key={item.label} className="px-2 py-2">
          <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-white/40">
            {item.label}
          </div>
          <motion.div
            key={`${item.label}-${item.value}`}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            className={`nums mt-1.5 font-mono text-[12px] ${item.tone === "profit" ? "text-[#00FF9D]" : "text-[#F8F8F8]"}`}
          >
            {item.value}
          </motion.div>
        </div>
      ))}
    </motion.div>
  );
}

export default function Hero() {
  return (
    <section className="relative min-h-[100svh] overflow-hidden bg-[#030303]">
      {/* Volumetric spotlight from the top */}
      <div className="absolute inset-0 bg-spotlight pointer-events-none" />
      <div className="absolute inset-0 bg-spotlight-bottom pointer-events-none" />

      {/* The intelligence core lives behind the entire hero */}
      <div className="absolute inset-0">
        <IntelligenceCore />
      </div>

      <div className="relative z-10 mx-auto flex min-h-[100svh] max-w-[1800px] flex-col justify-center px-5 py-24 sm:px-8 lg:px-14">
        <motion.p
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={spring}
          className="mb-7 font-mono text-[10px] uppercase tracking-[0.24em] text-white/45"
        >
          Sentinel / Autonomous Capital OS
        </motion.p>

        <motion.h1
          initial={{ opacity: 0, y: 34 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...spring, delay: 0.12 }}
          className="sentinel-hero-title"
        >
          AUTONOMOUS
          <br />
          INTELLIGENCE
          <br />
          FOR GLOBAL
          <br />
          MARKETS
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...spring, delay: 0.25 }}
          className="mt-7 max-w-[520px] text-[15px] leading-[1.6] text-white/70 sm:text-base"
        >
          The first autonomous operating system for market research, execution, and portfolio intelligence.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...spring, delay: 0.36 }}
          className="mt-8 flex flex-col gap-3 sm:flex-row"
        >
          <a href="/signup" className="liquid-button liquid-button-primary">
            <span>Launch Agent</span>
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M1 7h12M8 2l5 5-5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </a>
          <a href="#agents" className="liquid-button">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full rounded-full bg-[#00E5FF] opacity-60 animate-pulse-ring" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-[#00E5FF]" />
            </span>
            <span>View Intelligence Layer</span>
          </a>
        </motion.div>

        <StatusStripMobile />
      </div>

      {/* Desktop-only right-side glass status card */}
      <div className="absolute right-6 top-1/2 z-20 hidden -translate-y-1/2 lg:flex xl:right-12">
        <StatusCard />
      </div>

      {/* Scroll indicator */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1.4, duration: 1 }}
        className="absolute bottom-6 left-1/2 z-10 hidden -translate-x-1/2 flex-col items-center gap-2 sm:flex"
      >
        <span className="font-mono text-[9px] uppercase tracking-[0.24em] text-white/35">Scroll</span>
        <span className="block h-10 w-px bg-gradient-to-b from-white/30 to-transparent" />
      </motion.div>
    </section>
  );
}
