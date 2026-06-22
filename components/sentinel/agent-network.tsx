"use client";

import { motion } from "framer-motion";

/**
 * Agent Network — Radical Redesign.
 *
 * Instead of a centered SVG diagram, this is now a "Bento Chaos Grid"
 * where agent cards have wildly different sizes and visual treatments.
 * The section title is split across two lines at different sizes.
 * Each card has its own personality: gradients, patterns, big numbers.
 */

const SPRING = { type: "spring" as const, stiffness: 100, damping: 18, bounce: 0 };

type Agent = {
  num: string;
  name: string;
  role: string;
  scans: string[];
  /** Grid span on desktop: [columns, rows] */
  span: [number, number];
  /** Card personality */
  style: "gradient" | "bordered" | "filled" | "minimal";
};

const AGENTS: Agent[] = [
  {
    num: "01",
    name: "Research Agent",
    role: "Synthesizes the world into signal.",
    scans: ["News", "Filings", "Economic Data", "Social Signals"],
    span: [7, 2],
    style: "gradient",
  },
  {
    num: "02",
    name: "Signal Agent",
    role: "Generates opportunities.",
    scans: ["Regime Shift", "Flow Imbalance", "Volatility Edges"],
    span: [5, 1],
    style: "bordered",
  },
  {
    num: "03",
    name: "Risk Agent",
    role: "Calculates the cost of being wrong.",
    scans: ["Exposure", "Volatility", "Correlation"],
    span: [5, 1],
    style: "filled",
  },
  {
    num: "04",
    name: "Execution Agent",
    role: "Routes orders with zero ego.",
    scans: ["Routing", "Slippage", "Venue Quality"],
    span: [7, 2],
    style: "minimal",
  },
];

const cardStyles: Record<string, React.CSSProperties> = {
  gradient: {
    background:
      "linear-gradient(135deg, rgba(0,229,255,0.06) 0%, rgba(0,255,157,0.03) 50%, rgba(6,6,8,0.95) 100%)",
    border: "1px solid rgba(0,229,255,0.12)",
  },
  bordered: {
    background: "rgba(6,6,8,0.90)",
    border: "2px solid rgba(255,255,255,0.08)",
  },
  filled: {
    background:
      "linear-gradient(180deg, rgba(0,255,157,0.04) 0%, rgba(6,6,8,0.95) 100%)",
    border: "1px solid rgba(0,255,157,0.10)",
  },
  minimal: {
    background: "rgba(6,6,8,0.85)",
    border: "1px solid rgba(255,255,255,0.05)",
  },
};

const cardBackgrounds: Record<string, string> = {
  gradient: "",
  bordered: "bg-stripes-diagonal",
  filled: "bg-dots",
  minimal: "bg-mesh-gradient",
};

const enterDirections = [
  { x: -60, y: 40, rotate: -3 },
  { x: 60, y: -30, rotate: 2 },
  { x: -40, y: -50, rotate: 1.5 },
  { x: 80, y: 20, rotate: -2 },
];

function AgentCard({ agent, index }: { agent: Agent; index: number }) {
  const dir = enterDirections[index];
  const gridColumn = index < 2
    ? (index === 0 ? "span 7" : "span 5")
    : (index === 2 ? "span 5" : "span 7");

  return (
    <motion.article
      initial={{
        opacity: 0,
        x: dir.x,
        y: dir.y,
        rotate: dir.rotate,
      }}
      whileInView={{
        opacity: 1,
        x: 0,
        y: 0,
        rotate: 0,
      }}
      transition={{ ...SPRING, delay: index * 0.12 }}
      viewport={{ once: true, margin: "-10%" }}
      whileHover={{ scale: 1.02, y: -4 }}
      className={`relative overflow-hidden rounded-2xl sm:rounded-3xl p-5 sm:p-8 ${cardBackgrounds[agent.style]}`}
      style={{
        ...cardStyles[agent.style],
        gridColumn,
        gridRow: agent.span[1] > 1 ? "span 2" : "span 1",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        minHeight: agent.span[1] > 1 ? "340px" : "180px",
      }}
    >
      {/* Oversized ghost number */}
      <span
        className="absolute -right-4 -top-6 font-grotesk select-none pointer-events-none"
        style={{
          fontSize: agent.span[1] > 1 ? "clamp(100px, 14vw, 180px)" : "clamp(60px, 8vw, 100px)",
          fontWeight: 700,
          color: "rgba(255,255,255,0.025)",
          lineHeight: 1,
        }}
      >
        {agent.num}
      </span>

      {/* Pulse indicator */}
      <span className="agent-pulse" />

      {/* Content */}
      <div className="relative z-10 flex flex-col h-full justify-between">
        <div>
          <div className="flex items-center gap-2 mb-3">
            <span className="font-mono text-[9px] tracking-[0.28em] text-white/30 uppercase">
              AGENT {agent.num}
            </span>
            <span className="h-px flex-1 bg-white/[0.06]" />
          </div>

          <h3
            className="font-grotesk font-semibold tracking-[-0.03em] text-white"
            style={{
              fontSize: agent.span[1] > 1 ? "clamp(1.5rem, 3vw, 2.5rem)" : "clamp(1.1rem, 2vw, 1.6rem)",
            }}
          >
            {agent.name}
          </h3>

          <p
            className="mt-2 font-editorial italic text-white/50"
            style={{
              fontSize: agent.span[1] > 1 ? "clamp(0.9rem, 1.2vw, 1.1rem)" : "0.85rem",
            }}
          >
            {agent.role}
          </p>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {agent.scans.map((s) => (
            <span
              key={s}
              className="font-mono text-[9px] tracking-[0.18em] uppercase text-white/40 px-2.5 py-1 rounded-full border border-white/[0.06] bg-white/[0.02]"
            >
              {s}
            </span>
          ))}
        </div>
      </div>
    </motion.article>
  );
}

function TelemetryBar() {
  const details = [
    { metric: "Streams scanned", value: "18,400 / sec" },
    { metric: "Signal-to-noise", value: "94.2%" },
    { metric: "Sources", value: "1,284" },
    { metric: "Latency p99", value: "11ms" },
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      transition={{ ...SPRING, delay: 0.5 }}
      viewport={{ once: true }}
      className="mt-8 sm:mt-12 grid grid-cols-2 sm:grid-cols-4 gap-px overflow-hidden rounded-xl border border-white/[0.06] bg-white/[0.06]"
    >
      {details.map((d) => (
        <div key={d.metric} className="bg-[#030303]/90 p-4 sm:p-5">
          <span className="font-mono text-[9px] tracking-[0.2em] uppercase text-white/35 block">
            {d.metric}
          </span>
          <span className="nums font-grotesk text-lg sm:text-xl font-semibold text-white mt-1.5 block tracking-tight">
            {d.value}
          </span>
        </div>
      ))}
    </motion.div>
  );
}

export default function AgentNetwork() {
  return (
    <section id="agents" className="relative bg-[#030303] px-5 py-20 sm:px-8 sm:py-28 lg:py-36 overflow-hidden">
      <div className="diagonal-line" style={{ top: "8%", left: "-5%" }} />

      <div className="mx-auto max-w-[1400px]">
        {/* Title — split sizes, offset */}
        <div className="mb-12 sm:mb-20">
          <motion.span
            initial={{ opacity: 0, x: -20 }}
            whileInView={{ opacity: 1, x: 0 }}
            transition={SPRING}
            viewport={{ once: true }}
            className="font-mono text-[10px] uppercase tracking-[0.28em] text-[#00E5FF] block mb-6"
          >
            02 — Agent network
          </motion.span>

          <motion.div
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ ...SPRING, delay: 0.1 }}
            viewport={{ once: true }}
          >
            <span
              className="text-grotesk-display text-white block"
              style={{ fontSize: "clamp(3.5rem, 11vw, 12rem)" }}
            >
              FOUR
            </span>
            <span
              className="text-editorial-italic text-white/70 block -mt-2 sm:-mt-4 ml-[5vw]"
              style={{ fontSize: "clamp(2rem, 5vw, 5rem)" }}
            >
              minds, one system.
            </span>
          </motion.div>
        </div>

        {/* Bento chaos grid */}
        <div className="bento-chaos" style={{ gridAutoRows: "minmax(160px, auto)" }}>
          {AGENTS.map((agent, i) => (
            <AgentCard key={agent.num} agent={agent} index={i} />
          ))}
        </div>

        {/* Telemetry bar */}
        <TelemetryBar />
      </div>
    </section>
  );
}
