"use client";

import { useRef } from "react";
import { motion, useScroll, useTransform, useInView } from "framer-motion";

const AGENTS = [
  {
    id: "research",
    label: "Research Agent",
    role: "Perception",
    color: "#00D4FF",
    description:
      "Scans millions of market signals — filings, news, order flow, macro indicators.",
    output: "Market context delivered to Signal Agent.",
    thought: "Volatility regime shifting. Cross-asset correlation rising.",
    confidence: "98%",
  },
  {
    id: "signal",
    label: "Signal Agent",
    role: "Cognition",
    color: "#A78BFA",
    description:
      "Synthesizes the unstructured world into ranked, probability-weighted trade theses.",
    output: "High-conviction signal packet.",
    thought: "Thesis: long ITM, short OTM. Edge: 4.2σ.",
    confidence: "92%",
  },
  {
    id: "risk",
    label: "Risk Agent",
    role: "Discipline",
    color: "#FFB800",
    description:
      "Evaluates exposure, drawdown, and tail risk. Has absolute veto power over execution.",
    output: "Position sizing + stop logic approved.",
    thought: "Reduce exposure by 15%. Sector concentration breach.",
    confidence: "96%",
  },
  {
    id: "execution",
    label: "Execution Agent",
    role: "Action",
    color: "#00FF88",
    description:
      "Routes orders to the optimal venue, slices size, minimizes market impact.",
    output: "Filled. Slippage: 1.2 bps.",
    thought: "Routing to dark pool. Slicing 1,200 shares over 90s.",
    confidence: "99%",
  },
];

const ease = [0.16, 1, 0.3, 1] as const;

export default function OperatingSystem() {
  const containerRef = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    target: containerRef,
    offset: ["start start", "end end"],
  });

  return (
    <section
      id="system"
      ref={containerRef}
      className="relative bg-[#050505]"
    >
      {/* Section header */}
      <div className="mx-auto max-w-7xl px-6 lg:px-8 pt-32 pb-16">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.8, ease }}
          className="flex flex-col gap-6 max-w-3xl"
        >
          <div className="inline-flex items-center gap-2">
            <span className="h-px w-8 bg-accent" />
            <span className="text-[11px] font-mono uppercase tracking-[0.22em] text-accent">
              The Operating System
            </span>
          </div>
          <h2 className="font-display text-display-lg text-white text-balance">
            Four minds.
            <br />
            <span className="font-serif-italic text-ink-secondary">One capital stack.</span>
          </h2>
          <p className="text-[16px] text-ink-secondary max-w-xl leading-relaxed">
            A self-organizing hierarchy of specialized agents — each with a
            distinct cognitive role — communicating continuously to produce a
            single coherent action.
          </p>
        </motion.div>
      </div>

      {/* Sticky storytelling */}
      <div className="relative">
        <div className="mx-auto max-w-7xl px-6 lg:px-8">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12">
            {/* LEFT — sticky visual */}
            <div className="lg:col-span-5 lg:sticky lg:top-32 lg:self-start h-fit pb-16">
              <AgentFlowVisual scrollYProgress={scrollYProgress} />
            </div>

            {/* RIGHT — scrolling agent cards */}
            <div className="lg:col-span-7 flex flex-col gap-6 lg:gap-8 py-8 lg:py-16">
              {AGENTS.map((agent, i) => (
                <AgentCard
                  key={agent.id}
                  agent={agent}
                  index={i}
                  total={AGENTS.length}
                />
              ))}

              {/* Final outcome panel */}
              <motion.div
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-80px" }}
                transition={{ duration: 0.8, ease }}
                className="surface rounded-2xl p-8 lg:p-10"
              >
                <div className="flex items-center gap-3 mb-5">
                  <div className="h-1.5 w-1.5 rounded-full bg-success animate-pulse-soft" />
                  <span className="text-[11px] font-mono uppercase tracking-[0.22em] text-ink-tertiary">
                    Final outcome
                  </span>
                </div>
                <div className="flex flex-col gap-2">
                  <div className="font-display text-[36px] lg:text-[44px] text-white tracking-[-0.03em] leading-none">
                    Executed.
                  </div>
                  <p className="text-[14px] text-ink-secondary max-w-md leading-relaxed">
                    4,200 milliseconds from raw signal to cleared position. No
                    human in the loop. Every decision auditable, every risk
                    measured, every order optimal.
                  </p>
                </div>
                <div className="mt-8 grid grid-cols-3 gap-4 pt-6 border-t border-line">
                  {[
                    { k: "Cycle time", v: "4.2s" },
                    { k: "Slippage", v: "1.2 bps" },
                    { k: "Fill rate", v: "99.4%" },
                  ].map((x) => (
                    <div key={x.k} className="flex flex-col gap-1">
                      <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-ink-tertiary">
                        {x.k}
                      </span>
                      <span className="text-[18px] font-medium text-white nums">
                        {x.v}
                      </span>
                    </div>
                  ))}
                </div>
              </motion.div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function AgentCard({
  agent,
  index,
  total,
}: {
  agent: (typeof AGENTS)[number];
  index: number;
  total: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { margin: "-40% 0px -40% 0px", once: false });

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 32 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-100px" }}
      transition={{ duration: 0.7, ease }}
      className={`surface rounded-2xl p-7 lg:p-9 surface-hover ${
        inView ? "" : ""
      }`}
      style={{
        borderColor: inView ? `${agent.color}40` : undefined,
        boxShadow: inView
          ? `0 0 0 1px ${agent.color}20, 0 24px 64px -24px ${agent.color}30`
          : undefined,
        transition: "border-color 0.6s, box-shadow 0.6s",
      }}
    >
      {/* Step indicator */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <span
            className="text-[10px] font-mono uppercase tracking-[0.22em] nums"
            style={{ color: agent.color }}
          >
            0{index + 1} / 0{total}
          </span>
          <span className="h-3 w-px bg-line" />
          <span className="text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary">
            {agent.role}
          </span>
        </div>
        {index < total - 1 && (
          <span className="text-ink-tertiary text-lg leading-none">↓</span>
        )}
      </div>

      <h3 className="font-display text-[28px] lg:text-[34px] text-white tracking-[-0.025em] leading-[1.05]">
        {agent.label}
      </h3>

      <p className="mt-3 text-[15px] text-ink-secondary leading-relaxed max-w-xl">
        {agent.description}
      </p>

      {/* Terminal-style reasoning */}
      <div className="mt-7 rounded-xl border border-line bg-[#08080a] overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-2 border-b border-line bg-white/[0.02]">
          <div className="flex gap-1.5">
            <div className="h-2 w-2 rounded-full bg-white/15" />
            <div className="h-2 w-2 rounded-full bg-white/15" />
            <div className="h-2 w-2 rounded-full bg-white/15" />
          </div>
          <span
            className="text-[10px] font-mono uppercase tracking-[0.18em] ml-2"
            style={{ color: agent.color }}
          >
            reasoning.log
          </span>
        </div>
        <div className="p-5 font-mono text-[13px] leading-relaxed">
          <div className="text-ink-tertiary">
            <span style={{ color: agent.color }}>›</span> {agent.thought}
          </div>
          <div className="mt-2 text-ink-tertiary">
            <span style={{ color: agent.color }}>›</span> confidence:{" "}
            <span className="text-white nums">{agent.confidence}</span>
          </div>
          <div className="mt-2 text-ink-tertiary">
            <span style={{ color: agent.color }}>›</span> action:{" "}
            <span className="text-white">{agent.output}</span>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

function AgentFlowVisual({
  scrollYProgress,
}: {
  scrollYProgress: ReturnType<typeof useScroll>["scrollYProgress"];
}) {
  const lineHeight = useTransform(scrollYProgress, [0, 1], ["0%", "100%"]);

  return (
    <div className="relative surface rounded-2xl p-8 lg:p-10 overflow-hidden min-h-[520px]">
      <div className="text-[11px] font-mono uppercase tracking-[0.22em] text-ink-tertiary mb-1">
        Live Agent Stack
      </div>
      <div className="text-[14px] text-white/80 mb-10">Communication topology</div>

      {/* Vertical flow line */}
      <div className="absolute left-12 top-32 bottom-12 w-px bg-line" />
      <motion.div
        className="absolute left-12 top-32 w-px bg-gradient-to-b from-accent via-success to-accent"
        style={{ height: lineHeight }}
      />

      {/* Node stack */}
      <div className="flex flex-col gap-12">
        {AGENTS.map((agent, i) => (
          <div key={agent.id} className="flex items-start gap-5 relative">
            {/* Node dot */}
            <div className="relative z-10 flex-shrink-0">
              <div
                className="h-6 w-6 rounded-full border-2 flex items-center justify-center"
                style={{
                  borderColor: agent.color,
                  background: "#0E0E10",
                }}
              >
                <div
                  className="h-2 w-2 rounded-full"
                  style={{ background: agent.color }}
                />
              </div>
            </div>
            {/* Content */}
            <div className="flex-1 pt-0.5">
              <div
                className="text-[10px] font-mono uppercase tracking-[0.22em] mb-1"
                style={{ color: agent.color }}
              >
                {agent.role}
              </div>
              <div className="text-[15px] text-white font-medium tracking-[-0.01em]">
                {agent.label}
              </div>
              {i === 0 && (
                <div className="mt-2 text-[12px] text-ink-tertiary">
                  ← perceiving the market
                </div>
              )}
              {i === 1 && (
                <div className="mt-2 text-[12px] text-ink-tertiary">
                  ← forming the thesis
                </div>
              )}
              {i === 2 && (
                <div className="mt-2 text-[12px] text-ink-tertiary">
                  ← sizing the bet
                </div>
              )}
              {i === 3 && (
                <div className="mt-2 text-[12px] text-ink-tertiary">
                  ← hitting the market
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Decorative corner accent */}
      <div className="absolute top-4 right-4 text-[9px] font-mono uppercase tracking-[0.2em] text-ink-tertiary">
        T+0
      </div>
      <div className="absolute bottom-4 right-4 text-[9px] font-mono uppercase tracking-[0.2em] text-success">
        T+4.2s
      </div>
    </div>
  );
}
