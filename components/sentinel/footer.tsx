"use client";

import { motion } from "framer-motion";

/**
 * Sentinel Footer.
 *
 * 70vh tall. The word "SENTINEL" is rendered at 25vw (a typographic
 * monolith) at 4% opacity. Behind it, two rows of continuously-scrolling
 * market data streams create a sense of life and activity.
 *
 * Above the giant word, a small nav row with platform / company / legal
 * columns. Below, the standard copyright line.
 */

const SPRING = { type: "spring" as const, stiffness: 120, damping: 20, bounce: 0 };

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

const COLUMNS = [
  {
    title: "Platform",
    items: ["Intelligence Layer", "Agent Network", "Strategy Stack", "Decision Engine", "Execution API"],
  },
  {
    title: "Company",
    items: ["About", "Research", "Careers", "Press", "Contact"],
  },
  {
    title: "Legal",
    items: ["Terms", "Privacy", "Disclosures", "SOC 2", "Compliance"],
  },
];

function DataStream({ items, direction = "left", duration = "60s" }: { items: string[]; direction?: "left" | "right"; duration?: string }) {
  // Render the list twice so the marquee loop is seamless
  const list = [...items, ...items];
  return (
    <div className="data-stream-row" style={{ animationDuration: duration, animationDirection: direction === "right" ? "reverse" : "normal" }}>
      {list.map((t, i) => (
        <span key={i}>{t}</span>
      ))}
    </div>
  );
}

export default function Footer() {
  return (
    <footer className="relative flex min-h-[70vh] flex-col overflow-hidden bg-[#030303]">
      {/* Top: footer nav */}
      <div className="relative z-10 border-b border-white/[0.06] px-5 py-12 sm:px-8 sm:py-16">
        <div className="mx-auto grid max-w-7xl gap-10 sm:grid-cols-2 md:grid-cols-4">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.24em] text-white/40">
              Sentinel / Autonomous Capital OS
            </div>
            <p className="mt-4 max-w-xs text-sm text-white/55">
              The first autonomous operating system for market research, execution, and portfolio intelligence.
            </p>
            <div className="mt-6 flex items-center gap-2">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full rounded-full bg-[#00FF9D] opacity-60 animate-pulse-ring" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-[#00FF9D]" />
              </span>
              <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-white/55">
                All systems operational
              </span>
            </div>
          </div>

          {COLUMNS.map((col) => (
            <div key={col.title}>
              <p className="font-mono text-[10px] uppercase tracking-[0.24em] text-white/40">
                {col.title}
              </p>
              <ul className="mt-5 space-y-3">
                {col.items.map((item) => (
                  <li key={item}>
                    <a href="#" className="text-sm text-white/70 transition-colors duration-300 hover:text-white">
                      {item}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>

      {/* Giant SENTINEL word with data streams behind it */}
      <div className="relative z-0 flex flex-1 items-center justify-center overflow-hidden">
        <div className="data-streams mask-fade">
          <DataStream items={STREAM_A} duration="80s" />
          <DataStream items={STREAM_A} direction="right" duration="100s" />
          <DataStream items={STREAM_A} duration="90s" />
          <DataStream items={STREAM_A} direction="right" duration="120s" />
          <DataStream items={STREAM_A} duration="70s" />
        </div>
        <motion.p
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 0.04, y: 0 }}
          transition={SPRING}
          viewport={{ once: true }}
          className="select-none whitespace-nowrap text-center font-display text-[clamp(7rem,25vw,28rem)] font-medium leading-none tracking-[-0.06em] text-white"
        >
          SENTINEL
        </motion.p>
      </div>

      {/* Bottom: copyright */}
      <div className="relative z-10 border-t border-white/[0.06] px-5 py-6 sm:px-8">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-2 text-center sm:flex-row sm:text-left">
          <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/40">
            © 2026 Sentinel Capital Systems
          </span>
          <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/40">
            For research purposes only · Not investment advice
          </span>
        </div>
      </div>
    </footer>
  );
}
