"use client";

import { motion, useScroll, useTransform } from "framer-motion";
import { useRef } from "react";

/**
 * Agent Network — Section 2.
 *
 * A 400vh container with a sticky inner viewport. As the user scrolls:
 *   - the active agent is driven by the scroll progress (4 segments of 0.25)
 *   - each agent's "pulse" intensifies when active
 *   - the connecting line to the active agent fully draws in
 *   - the other 3 fade to 30% opacity
 *
 * On mobile (<md) the sticky layout collapses to a vertical feed of cards.
 */

const SPRING = { type: "spring" as const, stiffness: 120, damping: 20, bounce: 0 };

type Agent = {
  num: string;
  name: string;
  role: string;
  scans: string[];
  /** anchor in the 0..100 viewBox */
  pos: { x: number; y: number };
};

const AGENTS: Agent[] = [
  { num: "01", name: "Research Agent",  role: "Synthesizes the world into signal.",
    scans: ["News", "Filings", "Economic Data", "Social Signals"], pos: { x: 18, y: 22 } },
  { num: "02", name: "Signal Agent",    role: "Generates opportunities.",
    scans: ["Regime Shift", "Flow Imbalance", "Volatility Edges"], pos: { x: 78, y: 30 } },
  { num: "03", name: "Risk Agent",      role: "Calculates the cost of being wrong.",
    scans: ["Exposure", "Volatility", "Correlation"],            pos: { x: 24, y: 72 } },
  { num: "04", name: "Execution Agent", role: "Routes orders with zero ego.",
    scans: ["Routing", "Slippage", "Venue Quality"],             pos: { x: 76, y: 74 } },
];

function DesktopLayout() {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start start", "end end"],
  });

  // Active agent index changes every 0.25 of scroll progress
  const activeIndex = useTransform(scrollYProgress, (v) => {
    if (v < 0.25) return 0;
    if (v < 0.50) return 1;
    if (v < 0.75) return 2;
    return 3;
  });

  return (
    <div ref={ref} className="relative hidden h-[400vh] md:block">
      <div className="sticky top-0 flex h-screen items-center justify-center overflow-hidden">
        <div className="absolute inset-0 network-topology opacity-60 pointer-events-none" />

        {/* Eyebrow + title */}
        <div className="absolute left-8 top-8 z-10 lg:left-14">
          <motion.span
            initial={{ opacity: 0, y: 10 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={SPRING}
            viewport={{ once: true }}
            className="font-mono text-[10px] uppercase tracking-[0.24em] text-[#00E5FF]"
          >
            02 — Agent network
          </motion.span>
          <motion.h2
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ ...SPRING, delay: 0.1 }}
            viewport={{ once: true }}
            className="mt-4 max-w-2xl text-4xl font-medium tracking-[-0.04em] text-white sm:text-6xl lg:text-7xl"
          >
            Four minds.<br />One operating system.
          </motion.h2>
        </div>

        {/* Diagram */}
        <div className="relative h-[80vh] w-full max-w-6xl">
          {/* SVG: connection lines from center to each agent */}
          <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
            <defs>
              <linearGradient id="active-line" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#00E5FF" stopOpacity="0.0" />
                <stop offset="50%" stopColor="#00E5FF" stopOpacity="1" />
                <stop offset="100%" stopColor="#00E5FF" stopOpacity="0.0" />
              </linearGradient>
            </defs>

            {AGENTS.map((a, i) => (
              <ActiveLine
                key={a.num}
                from={{ x: a.pos.x, y: a.pos.y }}
                to={{ x: 50, y: 50 }}
                activeIndex={activeIndex}
                index={i}
              />
            ))}

            {/* Orbits around the center node */}
            <circle cx="50" cy="50" r="0.6" fill="#00E5FF" />
            <circle cx="50" cy="50" r="14" fill="none" stroke="rgba(0,229,255,0.18)" />
            <circle cx="50" cy="50" r="22" fill="none" stroke="rgba(0,229,255,0.10)" strokeDasharray="0.6 0.6" />
          </svg>

          {/* Center node */}
          <div className="agent-center">INTELLIGENCE<br />LAYER</div>

          {/* Agent nodes */}
          {AGENTS.map((agent, i) => (
            <ActiveNode
              key={agent.num}
              agent={agent}
              activeIndex={activeIndex}
              index={i}
            />
          ))}
        </div>

        {/* Active agent detail — bottom right */}
        <ActiveDetail activeIndex={activeIndex} />
      </div>
    </div>
  );
}

function ActiveLine({
  from, to, activeIndex, index,
}: { from: { x: number; y: number }; to: { x: number; y: number }; activeIndex: any; index: number }) {
  // Each line is a 0..1 progress; 1 when its index is active
  const progress = useTransform(activeIndex, (v: number) => (v === index ? 1 : 0.18));

  return (
    <motion.line
      x1={from.x} y1={from.y} x2={to.x} y2={to.y}
      stroke="#00E5FF"
      strokeWidth="0.18"
      strokeDasharray="0.6 0.6"
      style={{ pathLength: progress, opacity: progress }}
    />
  );
}

function ActiveNode({ agent, activeIndex, index }: { agent: Agent; activeIndex: any; index: number }) {
  const isActive = useTransform(activeIndex, (v: number) => v === index);
  const opacity = useTransform(isActive, (v: boolean) => (v ? 1 : 0.4));
  const scale  = useTransform(isActive, (v: boolean) => (v ? 1 : 0.96));

  return (
    <motion.div
      className="agent-node"
      style={{ left: `${agent.pos.x}%`, top: `${agent.pos.y}%`, opacity, scale }}
    >
      <span className="agent-pulse" />
      <div className="font-mono text-[10px] tracking-[0.22em] text-white/30">
        AGENT {agent.num}
      </div>
      <h3>{agent.name}</h3>
      {agent.scans.map((s) => (
        <p key={s}>{s}</p>
      ))}
    </motion.div>
  );
}

function ActiveDetail({ activeIndex }: { activeIndex: any }) {
  const details = [
    { metric: "Streams scanned",  value: "18,400 / sec" },
    { metric: "Signal-to-noise",  value: "94.2%"        },
    { metric: "Sources",          value: "1,284"        },
    { metric: "Latency p99",      value: "11ms"         },
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: 30 }}
      whileInView={{ opacity: 1, y: 0 }}
      transition={{ ...SPRING, delay: 0.3 }}
      viewport={{ once: true }}
      className="glass-card absolute bottom-10 right-8 z-10 hidden w-[320px] p-5 lg:block xl:right-14"
    >
      <div className="mb-4 font-mono text-[10px] uppercase tracking-[0.22em] text-white/45">
        Agent telemetry
      </div>
      <div className="space-y-3">
        {details.map((d) => (
          <div key={d.metric} className="flex items-end justify-between border-b border-white/[0.06] pb-3">
            <span className="text-[12px] text-white/55">{d.metric}</span>
            <span className="nums font-mono text-[12px] text-[#F8F8F8]">{d.value}</span>
          </div>
        ))}
      </div>
      <ActiveAgentName activeIndex={activeIndex} />
    </motion.div>
  );
}

function ActiveAgentName({ activeIndex }: { activeIndex: any }) {
  return (
    <motion.div
      key={String(activeIndex)}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="mt-4 flex items-center gap-2 border-t border-white/[0.06] pt-3"
    >
      <span className="h-1.5 w-1.5 rounded-full bg-[#00FF9D] shadow-[0_0_10px_#00FF9D]" />
      <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-white/55">
        Active ·{" "}
        <span className="text-white">{AGENTS[0].name}</span>
      </span>
    </motion.div>
  );
}

function MobileLayout() {
  return (
    <div className="md:hidden">
      <div className="px-5 pt-20 pb-12">
        <span className="font-mono text-[10px] uppercase tracking-[0.24em] text-[#00E5FF]">
          02 — Agent network
        </span>
        <h2 className="mt-4 text-4xl font-medium tracking-[-0.04em] text-white">
          Four minds.<br />One operating system.
        </h2>
        <p className="mt-4 text-white/55 max-w-sm">
          Each agent owns a single domain. Together they form the intelligence
          layer that observes, reasons, and acts.
        </p>
      </div>
      <div className="space-y-4 px-5 pb-24">
        {AGENTS.map((agent) => (
          <div key={agent.num} className="glass-card relative p-5">
            <span className="agent-pulse" />
            <div className="font-mono text-[10px] tracking-[0.22em] text-white/30">AGENT {agent.num}</div>
            <h3 className="mt-2 font-display text-2xl font-medium text-white">{agent.name}</h3>
            <p className="mt-1 text-sm text-white/55">{agent.role}</p>
            <div className="mt-4 space-y-1.5">
              {agent.scans.map((s) => (
                <p key={s} className="font-mono text-[10px] uppercase tracking-[0.18em] text-white/45">{s}</p>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function AgentNetwork() {
  return (
    <section id="agents" className="relative bg-[#030303]">
      <DesktopLayout />
      <MobileLayout />
    </section>
  );
}
