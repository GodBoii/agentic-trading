"use client";

import { useRef } from "react";
import { motion, useScroll, useTransform, useInView } from "framer-motion";

const STRATEGIES = [
  {
    id: "momentum",
    name: "Momentum Agent",
    blurb: "Captures directional moves with adaptive trend filters.",
    color: "#00D4FF",
    perf: "+28.4%",
    sharpe: "2.91",
    risk: "Medium",
    riskScore: 0.55,
    reasoning:
      "Trend persistence signal strengthening across 14 of 18 monitored instruments. Conviction: high.",
    data: [12, 14, 18, 16, 22, 26, 24, 30, 35, 33, 38, 42, 45, 48, 52, 56],
  },
  {
    id: "mean-reversion",
    name: "Mean Reversion Agent",
    blurb: "Exploits short-term statistical dislocations in correlated pairs.",
    color: "#A78BFA",
    perf: "+18.2%",
    sharpe: "2.45",
    risk: "Low",
    riskScore: 0.3,
    reasoning:
      "Z-score divergence on RELIANCE-BPCL reaching 2.8σ. Mean reversion probability: 78%.",
    data: [20, 22, 21, 24, 23, 26, 24, 28, 27, 30, 29, 32, 30, 33, 35, 36],
  },
  {
    id: "macro",
    name: "Macro Agent",
    blurb: "Positions around central bank cycles, inflation prints, and rate curves.",
    color: "#FFB800",
    perf: "+34.1%",
    sharpe: "1.87",
    risk: "High",
    riskScore: 0.75,
    reasoning:
      "Real yield inversion signal confirmed. Defensive tilt warranted; reducing duration by 40%.",
    data: [10, 12, 15, 14, 18, 17, 22, 20, 25, 28, 26, 32, 35, 38, 42, 46],
  },
  {
    id: "options",
    name: "Options Flow Agent",
    blurb: "Detects unusual options activity and implied volatility dislocations.",
    color: "#00FF88",
    perf: "+22.7%",
    sharpe: "3.12",
    risk: "Medium",
    riskScore: 0.5,
    reasoning:
      "Block trade detected: 14,200 call contracts on HDFCBANK. Dealers likely short gamma.",
    data: [15, 17, 16, 19, 22, 21, 24, 23, 27, 26, 30, 28, 32, 35, 33, 37],
  },
  {
    id: "stat-arb",
    name: "Statistical Arbitrage",
    blurb: "Cointegration-based pairs trading with sub-second rebalancing.",
    color: "#F472B6",
    perf: "+15.8%",
    sharpe: "3.84",
    risk: "Low",
    riskScore: 0.25,
    reasoning:
      "Cointegration breakdown on TCS-INFY pair. Half-life estimated at 4.2 sessions.",
    data: [18, 19, 20, 21, 22, 21, 23, 24, 23, 25, 26, 25, 27, 28, 27, 29],
  },
];

const ease = [0.16, 1, 0.3, 1] as const;

export default function Strategies() {
  return (
    <section
      id="strategies"
      className="relative bg-[#050505] py-32 overflow-hidden"
    >
      <div className="mx-auto max-w-7xl px-6 lg:px-8 mb-20">
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
              Strategy Library
            </span>
          </div>
          <h2 className="font-display text-display-lg text-white text-balance">
            Five strategies.
            <br />
            <span className="font-serif-italic text-ink-secondary">One intelligence.</span>
          </h2>
          <p className="text-[16px] text-ink-secondary max-w-xl leading-relaxed">
            Each strategy is a fully autonomous agent — self-evaluating,
            self-tuning, and self-restraining. Composed dynamically based on
            regime.
          </p>
        </motion.div>
      </div>

      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        {STRATEGIES.map((s, i) => (
          <StrategyCard key={s.id} strategy={s} index={i} />
        ))}
      </div>
    </section>
  );
}

function StrategyCard({
  strategy,
  index,
}: {
  strategy: (typeof STRATEGIES)[number];
  index: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { margin: "-30% 0px -30% 0px", once: false });

  return (
    <div
      ref={ref}
      className="sticky"
      style={{ top: `${100 + index * 12}px`, zIndex: index + 1 }}
    >
      <motion.div
        initial={{ opacity: 0, y: 40 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-80px" }}
        transition={{ duration: 0.7, ease }}
        className="mb-6"
      >
        <div
          className="surface rounded-2xl p-7 lg:p-10 transition-all duration-700 ease-out-expo"
          style={{
            borderColor: inView ? `${strategy.color}50` : undefined,
            boxShadow: inView
              ? `0 30px 80px -30px ${strategy.color}40, 0 0 0 1px ${strategy.color}25`
              : undefined,
            transform: inView ? "scale(1)" : "scale(0.98)",
          }}
        >
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
            {/* LEFT — meta + reasoning */}
            <div className="lg:col-span-5 flex flex-col">
              <div className="flex items-center gap-3 mb-5">
                <span
                  className="text-[10px] font-mono uppercase tracking-[0.22em] nums"
                  style={{ color: strategy.color }}
                >
                  0{index + 1} / 05
                </span>
                <span className="h-3 w-px bg-line" />
                <span className="text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary">
                  {strategy.risk} risk
                </span>
              </div>

              <h3 className="font-display text-[36px] lg:text-[44px] text-white tracking-[-0.03em] leading-[1] mb-4">
                {strategy.name}
              </h3>

              <p className="text-[15px] text-ink-secondary leading-relaxed">
                {strategy.blurb}
              </p>

              {/* AI reasoning block */}
              <div className="mt-7 pt-7 border-t border-line">
                <div className="text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary mb-2">
                  AI reasoning
                </div>
                <p
                  className="text-[13px] leading-relaxed font-mono"
                  style={{ color: strategy.color }}
                >
                  <span className="opacity-60">›</span> {strategy.reasoning}
                </p>
              </div>
            </div>

            {/* RIGHT — performance + chart */}
            <div className="lg:col-span-7 flex flex-col">
              {/* Stats row */}
              <div className="grid grid-cols-3 gap-4 pb-7 border-b border-line">
                <Stat label="12-mo return" value={strategy.perf} accent="text-success" />
                <Stat label="Sharpe" value={strategy.sharpe} accent="text-white" />
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-ink-tertiary">
                    Risk score
                  </span>
                  <div className="flex items-center gap-2">
                    <span className="text-[18px] font-medium text-white nums">
                      {Math.round(strategy.riskScore * 100)}
                    </span>
                    <div className="flex-1 h-1 bg-line rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-1000"
                        style={{
                          width: `${strategy.riskScore * 100}%`,
                          background: strategy.color,
                        }}
                      />
                    </div>
                  </div>
                </div>
              </div>

              {/* Custom chart — particle-wave blend */}
              <div className="pt-7 h-[220px]">
                <StrategyChart data={strategy.data} color={strategy.color} />
              </div>
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  );
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-ink-tertiary">
        {label}
      </span>
      <span className={`text-[22px] font-medium tracking-[-0.02em] nums ${accent}`}>
        {value}
      </span>
    </div>
  );
}

function StrategyChart({ data, color }: { data: number[]; color: string }) {
  const w = 600;
  const h = 200;
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const stepX = w / (data.length - 1);

  const points = data.map((v, i) => {
    const x = i * stepX;
    const y = h - ((v - min) / range) * (h - 30) - 15;
    return { x, y };
  });

  const linePath = points
    .map((p, i) => (i === 0 ? `M ${p.x} ${p.y}` : `L ${p.x} ${p.y}`))
    .join(" ");

  const areaPath = `${linePath} L ${w} ${h} L 0 ${h} Z`;

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-full" preserveAspectRatio="none">
      <defs>
        <linearGradient id={`grad-${color}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* Grid lines */}
      {[0.25, 0.5, 0.75].map((p) => (
        <line
          key={p}
          x1="0"
          y1={h * p}
          x2={w}
          y2={h * p}
          stroke="rgba(255,255,255,0.04)"
          strokeWidth="1"
          strokeDasharray="2 4"
        />
      ))}

      {/* Area fill */}
      <motion.path
        d={areaPath}
        fill={`url(#grad-${color})`}
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true }}
        transition={{ duration: 1.5, ease }}
      />

      {/* Line */}
      <motion.path
        d={linePath}
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        initial={{ pathLength: 0 }}
        whileInView={{ pathLength: 1 }}
        viewport={{ once: true }}
        transition={{ duration: 1.8, ease }}
      />

      {/* Data points — particles */}
      {points.map((p, i) => (
        <motion.circle
          key={i}
          cx={p.x}
          cy={p.y}
          r="2.5"
          fill={color}
          initial={{ opacity: 0, scale: 0 }}
          whileInView={{ opacity: 1, scale: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4, delay: 0.3 + i * 0.05, ease }}
        />
      ))}

      {/* End-point glow */}
      <motion.circle
        cx={points[points.length - 1].x}
        cy={points[points.length - 1].y}
        r="6"
        fill={color}
        opacity="0.3"
        initial={{ scale: 0 }}
        whileInView={{ scale: 1 }}
        viewport={{ once: true }}
        transition={{ duration: 0.6, delay: 1.5, ease }}
      >
        <animate
          attributeName="r"
          values="6;12;6"
          dur="2s"
          repeatCount="indefinite"
        />
        <animate
          attributeName="opacity"
          values="0.5;0.1;0.5"
          dur="2s"
          repeatCount="indefinite"
        />
      </motion.circle>
    </svg>
  );
}
