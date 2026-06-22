"use client";

import { motion } from "framer-motion";

/**
 * Footer — Radical Redesign.
 *
 * The giant SENTINEL word is now split across two lines, offset,
 * with individual letter opacity variations. Data streams are faster
 * and denser with varied colors. Footer nav links in an irregular
 * cloud. Noise texture overlay for grit.
 */

const SPRING = { type: "spring" as const, stiffness: 100, damping: 18, bounce: 0 };

const STREAM_A = [
  "AAPL  227.18  +0.84%",
  "MSFT  421.04  +1.22%",
  "NVDA  134.27  -0.46%",
  "TSLA  248.50  +2.11%",
  "GOOGL 178.92  +0.31%",
  "AMZN  198.64  +0.74%",
  "META  512.18  +1.62%",
  "BTC   64,201  -0.83%",
  "ETH   3,402   +0.45%",
  "SPX   5,489   +0.21%",
];

const STREAM_B = [
  "NDX   19,234  +0.32%",
  "VIX   13.42   -1.10%",
  "EUR   1.0712  -0.12%",
  "JPY   154.20  +0.08%",
  "GOLD  2,361   +0.40%",
  "OIL   78.42   -0.62%",
  "UST10 4.27%   +0.02",
  "UST02 4.84%   +0.01",
  "BTC.D 51.6%   -0.18%",
  "FUND  $12.4B  +24.8%",
];

const FOOTER_LINKS = [
  { title: "Intelligence Layer", category: "Platform" },
  { title: "Agent Network", category: "Platform" },
  { title: "Strategy Stack", category: "Platform" },
  { title: "Decision Engine", category: "Platform" },
  { title: "Execution API", category: "Platform" },
  { title: "About", category: "Company" },
  { title: "Research", category: "Company" },
  { title: "Careers", category: "Company" },
  { title: "Terms", category: "Legal" },
  { title: "Privacy", category: "Legal" },
  { title: "Disclosures", category: "Legal" },
  { title: "SOC 2", category: "Legal" },
];

function DataStream({
  items,
  direction = "left",
  duration = "60s",
  color = "cyan",
}: {
  items: string[];
  direction?: "left" | "right";
  duration?: string;
  color?: "cyan" | "green" | "orange";
}) {
  const list = [...items, ...items];
  const colorMap = {
    cyan: "rgba(0, 229, 255, 0.50)",
    green: "rgba(0, 255, 157, 0.40)",
    orange: "rgba(255, 184, 0, 0.35)",
  };

  return (
    <div
      className="data-stream-row"
      style={{
        animationDuration: duration,
        animationDirection: direction === "right" ? "reverse" : "normal",
        color: colorMap[color],
      }}
    >
      {list.map((t, i) => (
        <span key={i}>{t}</span>
      ))}
    </div>
  );
}

function PolycognitiveWordmark() {
  const word = "POLYCOGNITIVE";
  const opacities = [0.06, 0.04, 0.05, 0.03, 0.06, 0.04, 0.05, 0.03, 0.06, 0.04, 0.05, 0.03, 0.06];

  return (
    <div className="select-none pointer-events-none">
      {/* First line: "POLYCOG" offset left */}
      <div className="flex" style={{ marginLeft: "-2vw" }}>
        {word.slice(0, 7).split("").map((letter, i) => (
          <span
            key={`a-${i}`}
            className="font-grotesk font-bold"
            style={{
              fontSize: "clamp(4rem, 14vw, 18rem)",
              lineHeight: 0.82,
              letterSpacing: "-0.06em",
              color: `rgba(255,255,255,${opacities[i]})`,
            }}
          >
            {letter}
          </span>
        ))}
      </div>
      {/* Second line: "NITIVE" offset right */}
      <div className="flex justify-end" style={{ marginRight: "-3vw", marginTop: "-2vw" }}>
        {word.slice(7).split("").map((letter, i) => (
          <span
            key={`b-${i}`}
            className="font-editorial font-bold"
            style={{
              fontSize: "clamp(3rem, 12vw, 16rem)",
              lineHeight: 0.82,
              letterSpacing: "-0.04em",
              color: `rgba(255,255,255,${opacities[i + 7]})`,
            }}
          >
            {letter}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function Footer() {
  return (
    <footer className="relative flex min-h-[70vh] flex-col overflow-hidden bg-[#030303] noise-texture">
      {/* Top: footer nav — irregular cloud layout */}
      <div className="relative z-10 border-b border-white/[0.05] px-5 py-10 sm:px-8 sm:py-14">
        <div className="mx-auto max-w-[1400px]">
          {/* Brand */}
          <div className="flex items-start justify-between mb-10 sm:mb-14">
            <div>
              <div className="font-grotesk font-semibold text-sm tracking-[-0.01em] text-white/70">
                POLYCOGNITIVE
              </div>
              <p className="mt-2 max-w-xs text-[12px] text-white/40 font-grotesk leading-relaxed">
                The first autonomous operating system for market research,
                execution, and portfolio intelligence.
              </p>
              <div className="mt-4 flex items-center gap-2">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full rounded-full bg-[#00FF9D] opacity-60 animate-pulse-ring" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-[#00FF9D]" />
                </span>
                <span className="font-mono text-[9px] uppercase tracking-[0.22em] text-white/45">
                  All systems operational
                </span>
              </div>
            </div>
          </div>

          {/* Links — irregular cloud arrangement */}
          <div className="flex flex-wrap gap-x-6 gap-y-3 sm:gap-x-10 sm:gap-y-4">
            {FOOTER_LINKS.map((link, i) => (
              <a
                key={link.title}
                href="#"
                className="group flex items-center gap-2 transition-colors duration-300 hover:text-white"
                style={{
                  fontFamily: i % 3 === 0 ? "var(--font-grotesk)" : i % 3 === 1 ? "var(--font-mono)" : "var(--font-sans)",
                  fontSize: i % 4 === 0 ? "14px" : i % 4 === 1 ? "11px" : i % 4 === 2 ? "13px" : "10px",
                  color: `rgba(255,255,255,${0.3 + (i % 3) * 0.1})`,
                  letterSpacing: i % 2 === 0 ? "-0.01em" : "0.08em",
                  textTransform: i % 3 === 1 ? "uppercase" as const : "none" as const,
                }}
              >
                {link.title}
              </a>
            ))}
          </div>
        </div>
      </div>

      {/* Giant split SENTINEL with data streams behind */}
      <div className="relative z-0 flex flex-1 items-center justify-center overflow-hidden">
        <div className="data-streams mask-fade" style={{ opacity: 0.4 }}>
          <DataStream items={STREAM_A} duration="50s" color="cyan" />
          <DataStream items={STREAM_B} direction="right" duration="65s" color="green" />
          <DataStream items={STREAM_A} duration="55s" color="orange" />
          <DataStream items={STREAM_B} direction="right" duration="80s" color="cyan" />
          <DataStream items={STREAM_A} duration="45s" color="green" />
          <DataStream items={STREAM_B} direction="right" duration="70s" color="orange" />
          <DataStream items={STREAM_A} duration="60s" color="cyan" />
        </div>

        <motion.div
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={SPRING}
          viewport={{ once: true }}
          className="absolute inset-0 flex items-center justify-center"
        >
          <PolycognitiveWordmark />
        </motion.div>
      </div>

      {/* Bottom: copyright */}
      <div className="relative z-10 border-t border-white/[0.05] px-5 py-5 sm:px-8">
        <div className="mx-auto flex max-w-[1400px] flex-col items-center justify-between gap-2 text-center sm:flex-row sm:text-left">
          <span className="font-mono text-[9px] uppercase tracking-[0.24em] text-white/30">
            © 2026 Polycognitive Capital Systems
          </span>
          <span className="font-grotesk text-[10px] text-white/25">
            For research purposes only · Not investment advice
          </span>
        </div>
      </div>
    </footer>
  );
}
