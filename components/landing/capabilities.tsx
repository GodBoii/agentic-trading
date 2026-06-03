"use client";

import { motion } from "framer-motion";

const CAPABILITIES = [
  {
    n: "01",
    title: "Market Intelligence",
    blurb:
      "Continuously scans millions of market signals — filings, news, order flow, derivatives, and macro indicators — building a real-time model of the world.",
    tag: "Perception",
    color: "#00D4FF",
    metric: { k: "Signals / day", v: "1.4B+" },
  },
  {
    n: "02",
    title: "Autonomous Execution",
    blurb:
      "Executes trades with institutional precision. Smart order routing, dynamic slicing, and venue optimization minimize market impact.",
    tag: "Action",
    color: "#00FF88",
    metric: { k: "Avg slippage", v: "1.2 bps" },
  },
  {
    n: "03",
    title: "Dynamic Risk Control",
    blurb:
      "Adapts exposure in real time. Drawdown limits, sector concentration, tail-risk hedging — recalculated on every market tick.",
    tag: "Discipline",
    color: "#FFB800",
    metric: { k: "Max drawdown", v: "−4.8%" },
  },
  {
    n: "04",
    title: "Multi-Agent Collaboration",
    blurb:
      "Specialized AI agents coordinate strategies through structured communication. Each holds veto power where its domain demands it.",
    tag: "Cognition",
    color: "#A78BFA",
    metric: { k: "Active agents", v: "12" },
  },
  {
    n: "05",
    title: "Portfolio Optimization",
    blurb:
      "Allocates capital intelligently across strategies, instruments, and risk regimes — maximizing risk-adjusted return continuously.",
    tag: "Allocation",
    color: "#F472B6",
    metric: { k: "Sharpe ratio", v: "2.84" },
  },
  {
    n: "06",
    title: "Predictive Analytics",
    blurb:
      "Identifies opportunities before market consensus forms. Forecasts regime shifts, volatility expansions, and dislocations.",
    tag: "Foresight",
    color: "#FF5F57",
    metric: { k: "Edge vs consensus", v: "+18%" },
  },
];

const ease = [0.16, 1, 0.3, 1] as const;

export default function Capabilities() {
  return (
    <section id="agents" className="relative bg-[#050505] py-32 overflow-hidden">
      {/* Decorative gradient corner */}
      <div className="absolute -top-40 right-0 w-[600px] h-[600px] bg-accent/[0.04] rounded-full blur-[120px] pointer-events-none" />

      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.8, ease }}
          className="flex flex-col gap-6 max-w-3xl mb-20"
        >
          <div className="inline-flex items-center gap-2">
            <span className="h-px w-8 bg-accent" />
            <span className="text-[11px] font-mono uppercase tracking-[0.22em] text-accent">
              Agent Capabilities
            </span>
          </div>
          <h2 className="font-display text-display-lg text-white text-balance">
            Everything a quant desk does.
            <br />
            <span className="font-serif-italic text-ink-secondary">Faster. Tireless. Yours.</span>
          </h2>
        </motion.div>

        {/* Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-px bg-line rounded-3xl overflow-hidden border border-line">
          {CAPABILITIES.map((c, i) => (
            <motion.div
              key={c.n}
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-80px" }}
              transition={{ duration: 0.6, ease, delay: (i % 3) * 0.05 }}
              className="group relative bg-[#08080a] p-8 lg:p-10 transition-colors duration-700 ease-out-expo hover:bg-[#0c0c0e]"
            >
              {/* Top row: number + tag */}
              <div className="flex items-center justify-between mb-12">
                <span
                  className="text-[11px] font-mono tracking-[0.18em] nums"
                  style={{ color: c.color }}
                >
                  {c.n}
                </span>
                <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-ink-tertiary">
                  {c.tag}
                </span>
              </div>

              {/* Title */}
              <h3 className="font-display text-[26px] lg:text-[30px] text-white tracking-[-0.025em] leading-[1.1] mb-4">
                {c.title}
              </h3>

              {/* Blurb */}
              <p className="text-[14px] text-ink-secondary leading-relaxed mb-10">
                {c.blurb}
              </p>

              {/* Metric footer */}
              <div className="flex items-end justify-between pt-6 border-t border-line">
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-ink-tertiary">
                    {c.metric.k}
                  </span>
                  <span className="text-[20px] font-medium text-white tracking-[-0.02em] nums">
                    {c.metric.v}
                  </span>
                </div>
                {/* Color accent dot */}
                <div
                  className="h-2 w-2 rounded-full opacity-70 group-hover:opacity-100 transition-opacity"
                  style={{
                    background: c.color,
                    boxShadow: `0 0 12px ${c.color}80`,
                  }}
                />
              </div>

              {/* Hover glow */}
              <div
                className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-700 pointer-events-none rounded-none"
                style={{
                  background: `radial-gradient(600px circle at var(--x, 50%) var(--y, 50%), ${c.color}08 0%, transparent 40%)`,
                }}
              />
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
