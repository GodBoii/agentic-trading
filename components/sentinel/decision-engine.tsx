"use client";

import { motion } from "framer-motion";
import { useEffect, useState } from "react";

/**
 * Decision Engine — Radical Redesign.
 *
 * Dramatic 60/40 split. Left column has skewed headline.
 * Terminal panel has CRT scanline overlay with green phosphor.
 * Live stats are circular progress indicators.
 * Mixed typography chaos throughout.
 */

const SPRING = { type: "spring" as const, stiffness: 100, damping: 18, bounce: 0 };

type FeedLine = {
  time: string;
  message: string;
  confidence: string;
  action: string;
  status: "Completed" | "Monitoring" | "Queued";
};

const FEED: FeedLine[] = [
  { time: "09:34:12", message: "Volatility spike detected.", confidence: "91.4%", action: "Reduce exposure by 12%", status: "Completed" },
  { time: "09:34:18", message: "News sentiment diverges from price action.", confidence: "88.7%", action: "Hold execution window", status: "Monitoring" },
  { time: "09:34:26", message: "Liquidity river thinning near resistance.", confidence: "93.2%", action: "Route passive orders", status: "Completed" },
  { time: "09:34:31", message: "Correlation cluster expanding.", confidence: "89.9%", action: "Rebalance hedge sleeve", status: "Completed" },
  { time: "09:34:44", message: "Macro impulse confirms risk budget.", confidence: "94.1%", action: "Increase allocation by 4%", status: "Queued" },
  { time: "09:34:52", message: "Execution trail shows low slippage.", confidence: "97.8%", action: "Continue agent routing", status: "Completed" },
  { time: "09:35:01", message: "Skew compression across mega caps.", confidence: "86.5%", action: "Tilt toward upside convexity", status: "Monitoring" },
  { time: "09:35:09", message: "FX impulse confirms risk-on continuation.", confidence: "92.1%", action: "Scale into long bias", status: "Completed" },
  { time: "09:35:14", message: "ETF flow imbalance widening.", confidence: "90.6%", action: "Front-run institutional", status: "Queued" },
  { time: "09:35:22", message: "Volatility surface flattening.", confidence: "88.3%", action: "Tighten risk per unit", status: "Completed" },
];

function statusColor(s: FeedLine["status"]) {
  if (s === "Completed") return "#00FF9D";
  if (s === "Monitoring") return "#FFB800";
  return "#00E5FF";
}

function FeedRow({ line }: { line: FeedLine }) {
  return (
    <div className="terminal-line font-mono text-[10px] sm:text-[11px]" style={{ borderColor: "rgba(0,255,0,0.06)" }}>
      <div className="flex items-center gap-2 text-[#00FF9D]/40">
        <span>[{line.time}]</span>
        <span className="h-1 w-1 rounded-full bg-[#00FF9D]/30" />
        <span className="text-[9px] uppercase tracking-[0.2em]">POLYCOGNITIVE · REASON</span>
      </div>
      <p className="mt-2 text-[12px] font-sans text-[#00FF9D]/80 sm:text-[13px]">{line.message}</p>
      <div className="mt-2.5 grid grid-cols-1 gap-1 text-[#00FF9D]/50 sm:grid-cols-3 sm:gap-2">
        <span>
          Confidence: <b className="text-[#00FF9D]">{line.confidence}</b>
        </span>
        <span className="truncate">
          Action: <b className="text-[#00FF9D]/90">{line.action}</b>
        </span>
        <span>
          Status:{" "}
          <b style={{ color: statusColor(line.status) }}>{line.status}</b>
        </span>
      </div>
    </div>
  );
}

function CircularStat({ label, value, progress, delay }: { label: string; value: string; progress: number; delay: number }) {
  const r = 32;
  const c = 2 * Math.PI * r;
  const dashoffset = c * (1 - progress);

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.8 }}
      whileInView={{ opacity: 1, scale: 1 }}
      transition={{ ...SPRING, delay }}
      viewport={{ once: true }}
      className="flex flex-col items-center gap-2"
    >
      <div className="relative w-20 h-20 sm:w-24 sm:h-24">
        <svg className="w-full h-full -rotate-90" viewBox="0 0 80 80">
          <circle
            cx="40"
            cy="40"
            r={r}
            fill="none"
            stroke="rgba(255,255,255,0.05)"
            strokeWidth="3"
          />
          <motion.circle
            cx="40"
            cy="40"
            r={r}
            fill="none"
            stroke="#00E5FF"
            strokeWidth="3"
            strokeLinecap="round"
            strokeDasharray={c}
            initial={{ strokeDashoffset: c }}
            whileInView={{ strokeDashoffset: dashoffset }}
            transition={{ duration: 2, ease: [0.16, 1, 0.3, 1], delay: delay + 0.3 }}
            viewport={{ once: true }}
            style={{ filter: "drop-shadow(0 0 6px rgba(0,229,255,0.4))" }}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="nums font-grotesk text-sm sm:text-base font-bold text-white">{value}</span>
        </div>
      </div>
      <span className="font-mono text-[8px] sm:text-[9px] uppercase tracking-[0.2em] text-white/35 text-center">
        {label}
      </span>
    </motion.div>
  );
}

export default function DecisionEngine() {
  return (
    <section className="relative bg-[#030303] px-5 py-20 sm:px-8 sm:py-28 lg:py-36 overflow-hidden">
      <div className="diagonal-line" style={{ top: "15%", left: "-5%" }} />

      <div className="mx-auto grid max-w-[1400px] gap-10 lg:grid-cols-[1.1fr_0.9fr] lg:gap-16 items-start">
        {/* Left — dramatic editorial headline */}
        <div>
          <motion.span
            initial={{ opacity: 0, x: -20 }}
            whileInView={{ opacity: 1, x: 0 }}
            transition={SPRING}
            viewport={{ once: true }}
            className="font-mono text-[10px] uppercase tracking-[0.28em] text-[#00E5FF] block mb-6"
          >
            05 — Decision engine
          </motion.span>

          <motion.div
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ ...SPRING, delay: 0.1 }}
            viewport={{ once: true }}
            style={{ transform: "skewY(-1deg)" }}
          >
            <h2
              className="font-editorial font-bold tracking-[-0.04em] text-white"
              style={{ fontSize: "clamp(3rem, 7vw, 7rem)", lineHeight: 0.88 }}
            >
              Reasoning,
            </h2>
            <h2
              className="font-grotesk font-light tracking-[-0.03em] text-white/60 -mt-1"
              style={{ fontSize: "clamp(2rem, 5vw, 5rem)", lineHeight: 0.9 }}
            >
              not reacting.
            </h2>
          </motion.div>

          <motion.p
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ ...SPRING, delay: 0.2 }}
            viewport={{ once: true }}
            className="mt-8 max-w-md text-white/45 font-grotesk text-sm sm:text-base leading-relaxed"
          >
            Every action is grounded in a chain of evidence. Every confidence
            number is auditable. Every execution is explainable.
          </motion.p>

          {/* Circular stats */}
          <div className="mt-10 sm:mt-14 flex items-start gap-6 sm:gap-10">
            <CircularStat label="Decisions / sec" value="6" progress={0.75} delay={0} />
            <CircularStat label="Avg Latency" value="11ms" progress={0.12} delay={0.1} />
            <CircularStat label="Active Threads" value="1,284" progress={0.92} delay={0.2} />
          </div>
        </div>

        {/* Right — CRT Terminal */}
        <motion.div
          initial={{ opacity: 0, y: 40, rotate: 1 }}
          whileInView={{ opacity: 1, y: 0, rotate: 0 }}
          transition={{ ...SPRING, delay: 0.2 }}
          viewport={{ once: true, margin: "-10%" }}
          className="terminal-panel crt-overlay relative h-[480px] sm:h-[580px] overflow-hidden"
          style={{
            background: "rgba(0, 8, 2, 0.90)",
            borderColor: "rgba(0,255,0,0.08)",
            boxShadow:
              "0 40px 100px -30px rgba(0,0,0,0.9), inset 0 0 60px rgba(0,255,0,0.02)",
          }}
        >
          {/* Terminal header with green phosphor feel */}
          <div
            className="sticky top-0 z-10 flex items-center justify-between border-b px-5 py-3 backdrop-blur-md"
            style={{
              borderColor: "rgba(0,255,0,0.08)",
              background: "rgba(0, 6, 2, 0.92)",
            }}
          >
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-[#FF5B5B]" />
              <span className="h-2 w-2 rounded-full bg-[#FFB800]" />
              <span className="h-2 w-2 rounded-full bg-[#00FF9D]" />
              <span className="ml-2 font-mono text-[9px] uppercase tracking-[0.22em] text-[#00FF9D]/40">
                polycognitive.terminal
              </span>
            </div>
            <span className="hidden font-mono text-[9px] uppercase tracking-[0.22em] text-[#00FF9D]/35 sm:flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-[#00FF9D] shadow-[0_0_8px_#00FF9D] animate-pulse-soft" />
              Streaming
            </span>
          </div>

          {/* Scrolling feed — green phosphor text */}
          <div className="relative h-[calc(100%-44px)] overflow-hidden">
            <motion.div
              animate={{ y: ["0%", "-50%"] }}
              transition={{ duration: 35, ease: "linear", repeat: Infinity }}
              className="absolute inset-x-0 top-0 space-y-2.5 p-4 sm:p-5"
            >
              {[...FEED, ...FEED].map((line, i) => (
                <FeedRow key={`${line.time}-${i}`} line={line} />
              ))}
            </motion.div>

            {/* Fade overlays */}
            <div
              className="pointer-events-none absolute inset-x-0 top-0 h-16"
              style={{ background: "linear-gradient(to bottom, rgba(0,6,2,1), transparent)" }}
            />
            <div
              className="pointer-events-none absolute inset-x-0 bottom-0 h-16"
              style={{ background: "linear-gradient(to top, rgba(0,6,2,1), transparent)" }}
            />
          </div>
        </motion.div>
      </div>
    </section>
  );
}
