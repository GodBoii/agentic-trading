"use client";

import { motion } from "framer-motion";

/**
 * Strategy Stack — Section 4.
 *
 * 5 sticky cards stacked on top of each other. Each card reveals as the
 * user scrolls; the next one "covers" the previous via the sticky offset.
 * Each card carries:
 *   - card index (Card 01..05)
 *   - strategy name
 *   - performance graph (sparkline)
 *   - Sharpe ratio + win rate
 *   - agent commentary
 *   - animated market preview block
 */

const SPRING = { type: "spring" as const, stiffness: 120, damping: 20, bounce: 0 };

type Strategy = {
  num: string;
  name: string;
  category: string;
  sharpe: string;
  win: string;
  ytd: string;
  note: string;
  /** normalized 0..1 series for the sparkline */
  series: number[];
  /** accent for this card (cyan / green / mixed) */
  accent: "cyan" | "green";
};

const STRATEGIES: Strategy[] = [
  {
    num: "01", name: "Momentum Intelligence", category: "Equities · Mid-Cap",
    sharpe: "2.71", win: "68.4%", ytd: "+18.9%",
    note: "Signal velocity rising across liquid mid-cap universe.",
    series: [0.2, 0.25, 0.3, 0.28, 0.42, 0.5, 0.55, 0.6, 0.66, 0.72, 0.7, 0.82, 0.9],
    accent: "cyan",
  },
  {
    num: "02", name: "Market Structure", category: "Order Flow",
    sharpe: "2.18", win: "64.9%", ytd: "+12.6%",
    note: "Liquidity pockets identified below current pressure band.",
    series: [0.4, 0.45, 0.42, 0.5, 0.48, 0.55, 0.6, 0.58, 0.65, 0.7, 0.68, 0.74, 0.78],
    accent: "cyan",
  },
  {
    num: "03", name: "Cross Asset Flow", category: "Multi-Asset",
    sharpe: "2.94", win: "71.2%", ytd: "+22.4%",
    note: "FX impulse confirms equity risk-on continuation.",
    series: [0.3, 0.35, 0.45, 0.5, 0.55, 0.5, 0.6, 0.68, 0.74, 0.78, 0.85, 0.88, 0.95],
    accent: "green",
  },
  {
    num: "04", name: "Options Intelligence", category: "Derivatives",
    sharpe: "1.96", win: "62.8%", ytd: "+9.8%",
    note: "Skew compression suggests controlled upside convexity.",
    series: [0.5, 0.45, 0.48, 0.52, 0.5, 0.55, 0.58, 0.6, 0.55, 0.62, 0.65, 0.68, 0.7],
    accent: "cyan",
  },
  {
    num: "05", name: "Macro Engine", category: "Rates · FX · Commodities",
    sharpe: "3.11", win: "73.6%", ytd: "+26.1%",
    note: "Rates repricing absorbed; allocation bias remains constructive.",
    series: [0.25, 0.3, 0.4, 0.5, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.92, 0.98],
    accent: "green",
  },
];

function Sparkline({ series, accent }: { series: number[]; accent: "cyan" | "green" }) {
  const W = 100, H = 30;
  const points = series.map((v, i) => {
    const x = (i / (series.length - 1)) * W;
    const y = H - v * H * 0.85 - 2;
    return `${x},${y}`;
  }).join(" ");
  const last = series[series.length - 1];
  const lastX = W;
  const lastY = H - last * H * 0.85 - 2;
  const stroke = accent === "green" ? "#00FF9D" : "#00E5FF";

  return (
    <div className="strategy-preview">
      {/* animated micro-orb in the preview */}
      <span className="preview-pulse" style={{ left: "20%", top: "30%" }} />
      <span className="preview-pulse" style={{ left: "55%", top: "50%", animationDelay: "-1.5s" }} />
      <span className="preview-pulse" style={{ left: "78%", top: "22%", animationDelay: "-3s" }} />

      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="preview-spark">
        <defs>
          <linearGradient id={`grad-${accent}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={stroke} stopOpacity="0.45" />
            <stop offset="100%" stopColor={stroke} stopOpacity="0" />
          </linearGradient>
        </defs>
        <polygon
          points={`0,${H} ${points} ${W},${H}`}
          fill={`url(#grad-${accent})`}
        />
        <polyline
          points={points}
          fill="none"
          stroke={stroke}
          strokeWidth="0.6"
          strokeLinecap="round"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
        />
        <circle cx={lastX} cy={lastY} r="0.9" fill={stroke} />
        <circle cx={lastX} cy={lastY} r="2.4" fill={stroke} opacity="0.25">
          <animate attributeName="r" values="2.4;4;2.4" dur="2.4s" repeatCount="indefinite" />
          <animate attributeName="opacity" values="0.25;0;0.25" dur="2.4s" repeatCount="indefinite" />
        </circle>
      </svg>

      <div className="absolute left-4 top-4 font-mono text-[9px] uppercase tracking-[0.2em] text-white/35">
        30D · 1D resolution
      </div>
      <div className="absolute right-4 top-4 font-mono text-[10px] text-white/55">
        <span className="text-[#F8F8F8]">+{((last - series[0]) * 100).toFixed(1)}%</span>
      </div>
    </div>
  );
}

function Card({ strategy, index }: { strategy: Strategy; index: number }) {
  // Each subsequent card sits a bit further down so the stack has a sense of depth
  const top = 96 + index * 18;

  return (
    <motion.article
      initial={{ opacity: 0.6, y: 40 }}
      whileInView={{ opacity: 1, y: 0 }}
      transition={{ ...SPRING, delay: index * 0.05 }}
      viewport={{ once: true, margin: "-10%" }}
      className="strategy-card relative p-6 sm:p-10"
      style={{ top: `${top}px` }}
    >
      <div className="grid gap-8 lg:grid-cols-[1fr_1.2fr]">
        <div>
          <div className="flex items-center gap-3">
            <span className="font-mono text-[10px] tracking-[0.24em] text-white/40">CARD {strategy.num}</span>
            <span className="h-px flex-1 bg-white/10" />
            <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-white/35">
              {strategy.category}
            </span>
          </div>
          <h3 className="mt-5 text-3xl font-medium tracking-[-0.03em] text-white sm:text-5xl">
            {strategy.name}
          </h3>

          <div className="mt-7 grid grid-cols-3 gap-4">
            <div>
              <p className="text-[10px] uppercase tracking-[0.2em] text-white/35">Sharpe</p>
              <p className="nums mt-2 text-2xl text-[#00FF9D] sm:text-3xl">{strategy.sharpe}</p>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-[0.2em] text-white/35">Win rate</p>
              <p className="nums mt-2 text-2xl text-white sm:text-3xl">{strategy.win}</p>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-[0.2em] text-white/35">YTD</p>
              <p className="nums mt-2 text-2xl text-[#00E5FF] sm:text-3xl">{strategy.ytd}</p>
            </div>
          </div>

          <div className="mt-7 flex items-start gap-3 rounded-xl border border-white/[0.07] bg-white/[0.02] p-4">
            <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#00FF9D] shadow-[0_0_8px_#00FF9D]" />
            <p className="text-sm leading-relaxed text-white/70">
              <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-white/35">Agent commentary · </span>
              {strategy.note}
            </p>
          </div>
        </div>

        <div>
          <Sparkline series={strategy.series} accent={strategy.accent} />
        </div>
      </div>
    </motion.article>
  );
}

export default function StrategyStack() {
  return (
    <section id="strategies" className="relative bg-[#030303] px-5 py-24 sm:px-8 sm:py-32">
      <div className="mx-auto max-w-6xl">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={SPRING}
          viewport={{ once: true, margin: "-20%" }}
          className="mb-14 sm:mb-20"
        >
          <span className="font-mono text-[10px] uppercase tracking-[0.24em] text-[#00E5FF]">
            04 — Strategy stack
          </span>
          <h2 className="mt-4 max-w-3xl text-4xl font-medium tracking-[-0.04em] text-white sm:text-6xl lg:text-7xl">
            Five strategies.<br />Compounding.
          </h2>
          <p className="mt-5 max-w-xl text-white/55">
            Capital is allocated by signal, not by story. Each strategy is independently governed, risk-bounded, and continuously re-weighted.
          </p>
        </motion.div>

        <div className="relative pb-12">
          {STRATEGIES.map((s, i) => (
            <Card key={s.num} strategy={s} index={i} />
          ))}
        </div>
      </div>
    </section>
  );
}
