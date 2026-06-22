"use client";

import { motion, useScroll, useTransform } from "framer-motion";
import { useRef } from "react";

/**
 * Strategy Stack — Radical Redesign.
 *
 * Horizontal scroll carousel with wildly uneven card sizes.
 * Each card has a different background treatment.
 * Numbers oversized and clipping outside containers.
 * Mixed typography throughout.
 */

const SPRING = { type: "spring" as const, stiffness: 100, damping: 18, bounce: 0 };

type Strategy = {
  num: string;
  name: string;
  category: string;
  sharpe: string;
  win: string;
  ytd: string;
  note: string;
  series: number[];
  accent: "cyan" | "green";
  /** Card dimensions */
  width: string;
  height: string;
  /** Visual treatment */
  bg: "stripes" | "dots" | "gradient" | "mesh" | "plain";
};

const STRATEGIES: Strategy[] = [
  {
    num: "01",
    name: "Momentum Intelligence",
    category: "Equities · Mid-Cap",
    sharpe: "2.71",
    win: "68.4%",
    ytd: "+18.9%",
    note: "Signal velocity rising across liquid mid-cap universe.",
    series: [0.2, 0.25, 0.3, 0.28, 0.42, 0.5, 0.55, 0.6, 0.66, 0.72, 0.7, 0.82, 0.9],
    accent: "cyan",
    width: "420px",
    height: "520px",
    bg: "gradient",
  },
  {
    num: "02",
    name: "Market Structure",
    category: "Order Flow",
    sharpe: "2.18",
    win: "64.9%",
    ytd: "+12.6%",
    note: "Liquidity pockets identified below current pressure band.",
    series: [0.4, 0.45, 0.42, 0.5, 0.48, 0.55, 0.6, 0.58, 0.65, 0.7, 0.68, 0.74, 0.78],
    accent: "cyan",
    width: "340px",
    height: "380px",
    bg: "stripes",
  },
  {
    num: "03",
    name: "Cross Asset Flow",
    category: "Multi-Asset",
    sharpe: "2.94",
    win: "71.2%",
    ytd: "+22.4%",
    note: "FX impulse confirms equity risk-on continuation.",
    series: [0.3, 0.35, 0.45, 0.5, 0.55, 0.5, 0.6, 0.68, 0.74, 0.78, 0.85, 0.88, 0.95],
    accent: "green",
    width: "480px",
    height: "460px",
    bg: "dots",
  },
  {
    num: "04",
    name: "Options Intelligence",
    category: "Derivatives",
    sharpe: "1.96",
    win: "62.8%",
    ytd: "+9.8%",
    note: "Skew compression suggests controlled upside convexity.",
    series: [0.5, 0.45, 0.48, 0.52, 0.5, 0.55, 0.58, 0.6, 0.55, 0.62, 0.65, 0.68, 0.7],
    accent: "cyan",
    width: "360px",
    height: "540px",
    bg: "mesh",
  },
  {
    num: "05",
    name: "Macro Engine",
    category: "Rates · FX · Commodities",
    sharpe: "3.11",
    win: "73.6%",
    ytd: "+26.1%",
    note: "Rates repricing absorbed; allocation bias remains constructive.",
    series: [0.25, 0.3, 0.4, 0.5, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.92, 0.98],
    accent: "green",
    width: "440px",
    height: "420px",
    bg: "plain",
  },
];

const bgClasses: Record<string, string> = {
  stripes: "bg-stripes-diagonal",
  dots: "bg-dots",
  gradient: "",
  mesh: "bg-mesh-gradient",
  plain: "",
};

const bgStyles: Record<string, React.CSSProperties> = {
  gradient: {
    background:
      "linear-gradient(160deg, rgba(0,229,255,0.05) 0%, rgba(6,6,8,0.95) 40%, rgba(0,255,157,0.03) 100%)",
  },
  stripes: { background: "rgba(6,6,8,0.92)" },
  dots: { background: "rgba(6,6,8,0.90)" },
  mesh: { background: "rgba(6,6,8,0.88)" },
  plain: {
    background:
      "linear-gradient(180deg, rgba(0,255,157,0.04) 0%, rgba(6,6,8,0.96) 100%)",
  },
};

function Sparkline({ series, accent }: { series: number[]; accent: "cyan" | "green" }) {
  const W = 200,
    H = 60;
  const points = series
    .map((v, i) => {
      const x = (i / (series.length - 1)) * W;
      const y = H - v * H * 0.85 - 4;
      return `${x},${y}`;
    })
    .join(" ");
  const last = series[series.length - 1];
  const lastX = W;
  const lastY = H - last * H * 0.85 - 4;
  const stroke = accent === "green" ? "#00FF9D" : "#00E5FF";

  return (
    <div className="absolute bottom-0 left-0 right-0 h-[40%] overflow-hidden">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="absolute inset-0 w-full h-full">
        <defs>
          <linearGradient id={`spark-fill-${accent}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={stroke} stopOpacity="0.25" />
            <stop offset="100%" stopColor={stroke} stopOpacity="0" />
          </linearGradient>
        </defs>
        <polygon points={`0,${H} ${points} ${W},${H}`} fill={`url(#spark-fill-${accent})`} />
        <polyline
          points={points}
          fill="none"
          stroke={stroke}
          strokeWidth="1"
          strokeLinecap="round"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
        />
        <circle cx={lastX} cy={lastY} r="2" fill={stroke} />
        <circle cx={lastX} cy={lastY} r="5" fill={stroke} opacity="0.2">
          <animate attributeName="r" values="5;9;5" dur="2.4s" repeatCount="indefinite" />
          <animate attributeName="opacity" values="0.2;0;0.2" dur="2.4s" repeatCount="indefinite" />
        </circle>
      </svg>
    </div>
  );
}

function StrategyCard({ strategy, index }: { strategy: Strategy; index: number }) {
  return (
    <motion.article
      initial={{ opacity: 0, y: 40, rotate: index % 2 === 0 ? -1 : 1 }}
      whileInView={{ opacity: 1, y: 0, rotate: 0 }}
      transition={{ ...SPRING, delay: index * 0.08 }}
      viewport={{ once: true, margin: "-5%" }}
      whileHover={{ scale: 1.03, y: -8 }}
      className={`relative overflow-hidden rounded-2xl sm:rounded-3xl ${bgClasses[strategy.bg]}`}
      style={{
        ...bgStyles[strategy.bg],
        width: strategy.width,
        height: strategy.height,
        border: "1px solid rgba(255,255,255,0.07)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        boxShadow: "0 40px 100px -40px rgba(0,0,0,0.8)",
      }}
    >
      {/* Oversized ghost number — clips outside */}
      <span
        className="absolute -right-3 -top-8 font-grotesk font-bold select-none pointer-events-none"
        style={{
          fontSize: "clamp(120px, 16vw, 200px)",
          color: "rgba(255,255,255,0.02)",
          lineHeight: 0.8,
        }}
      >
        {strategy.num}
      </span>

      {/* Card content */}
      <div className="relative z-10 p-5 sm:p-7 flex flex-col h-full">
        <div className="flex items-center gap-2 mb-3">
          <span className="font-mono text-[9px] tracking-[0.24em] text-white/30 uppercase">
            CARD {strategy.num}
          </span>
          <span className="h-px flex-1 bg-white/[0.06]" />
          <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-white/25">
            {strategy.category}
          </span>
        </div>

        <h3
          className="font-grotesk font-semibold tracking-[-0.03em] text-white"
          style={{ fontSize: "clamp(1.2rem, 2.5vw, 2rem)" }}
        >
          {strategy.name}
        </h3>

        {/* Metrics row — sizes deliberately uneven */}
        <div className="mt-5 grid grid-cols-3 gap-3">
          <div>
            <p className="font-mono text-[8px] uppercase tracking-[0.2em] text-white/30">Sharpe</p>
            <p className="nums font-grotesk text-2xl sm:text-3xl font-bold text-[#00FF9D] mt-1">
              {strategy.sharpe}
            </p>
          </div>
          <div>
            <p className="font-mono text-[8px] uppercase tracking-[0.2em] text-white/30">Win rate</p>
            <p className="nums font-grotesk text-lg sm:text-xl font-medium text-white mt-1">
              {strategy.win}
            </p>
          </div>
          <div>
            <p className="font-mono text-[8px] uppercase tracking-[0.2em] text-white/30">YTD</p>
            <p className="nums font-grotesk text-sm sm:text-base text-[#00E5FF] mt-1">
              {strategy.ytd}
            </p>
          </div>
        </div>

        {/* Agent commentary */}
        <div className="mt-4 flex items-start gap-2 p-3 rounded-lg border border-white/[0.05] bg-white/[0.015]">
          <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#00FF9D] shadow-[0_0_8px_#00FF9D]" />
          <p className="text-[12px] leading-relaxed text-white/55">
            <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-white/30">
              Agent ·{" "}
            </span>
            {strategy.note}
          </p>
        </div>

        {/* Sparkline fills the bottom */}
        <div className="flex-1" />
      </div>

      <Sparkline series={strategy.series} accent={strategy.accent} />
    </motion.article>
  );
}

export default function StrategyStack() {
  const scrollRef = useRef<HTMLDivElement>(null);

  return (
    <section id="strategies" className="relative bg-[#030303] py-20 sm:py-28 lg:py-36 overflow-hidden">
      <div className="px-5 sm:px-8 lg:px-14 mx-auto max-w-[1400px]">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={SPRING}
          viewport={{ once: true, margin: "-20%" }}
          className="mb-10 sm:mb-14"
        >
          <span className="font-mono text-[10px] uppercase tracking-[0.28em] text-[#00E5FF] block mb-5">
            04 — Strategy stack
          </span>

          {/* Title: deliberately uneven sizes */}
          <div className="flex flex-col sm:flex-row sm:items-baseline gap-2 sm:gap-5">
            <span
              className="text-grotesk-display text-white"
              style={{ fontSize: "clamp(3rem, 8vw, 8rem)" }}
            >
              FIVE
            </span>
            <span
              className="text-editorial-italic text-white/60"
              style={{ fontSize: "clamp(1.5rem, 3.5vw, 3.5rem)" }}
            >
              strategies, compounding.
            </span>
          </div>

          <p className="mt-5 max-w-xl text-white/45 font-grotesk text-sm sm:text-base">
            Capital is allocated by signal, not by story. Each strategy is independently governed,
            risk-bounded, and continuously re-weighted.
          </p>
        </motion.div>
      </div>

      {/* Horizontal scroll carousel */}
      <div
        ref={scrollRef}
        className="horizontal-scroll px-5 sm:px-8 lg:px-14 pb-4"
        style={{ alignItems: "flex-end" }}
      >
        {STRATEGIES.map((s, i) => (
          <StrategyCard key={s.num} strategy={s} index={i} />
        ))}
        {/* Spacer at end */}
        <div style={{ width: "40px", flexShrink: 0 }} />
      </div>

      {/* Scroll hint */}
      <div className="px-5 sm:px-8 lg:px-14 mt-6">
        <div className="mx-auto max-w-[1400px] flex items-center gap-3">
          <span className="font-mono text-[9px] tracking-[0.24em] uppercase text-white/25">
            Scroll →
          </span>
          <div className="h-px flex-1 bg-gradient-to-r from-white/10 to-transparent" />
        </div>
      </div>
    </section>
  );
}
