"use client";

import { motion } from "framer-motion";
import { useEffect, useRef } from "react";

const ease = [0.16, 1, 0.3, 1] as const;

export default function Performance() {
  return (
    <section
      id="performance"
      className="relative bg-[#050505] py-32 overflow-hidden"
    >
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
              Performance
            </span>
          </div>
          <h2 className="font-display text-display-lg text-white text-balance">
            Capital flow,
            <br />
            <span className="font-serif-italic text-ink-secondary">visualized.</span>
          </h2>
          <p className="text-[16px] text-ink-secondary max-w-xl leading-relaxed">
            Not charts. Proprietary visualizations — blending execution flow,
            liquidity depth, and AI decision trails into a single canvas.
          </p>
        </motion.div>

        {/* Visualization grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Main: large equity curve */}
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-80px" }}
            transition={{ duration: 0.8, ease }}
            className="lg:col-span-8 surface rounded-3xl p-8 lg:p-10 relative overflow-hidden"
          >
            <div className="flex items-center justify-between mb-6">
              <div>
                <div className="text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary mb-1.5">
                  Equity · 12 months
                </div>
                <div className="flex items-baseline gap-3">
                  <span className="font-display text-[40px] text-white tracking-[-0.03em] leading-none nums">
                    ₹14,82,650
                  </span>
                  <span className="text-[13px] text-success nums">
                    +48.2%
                  </span>
                </div>
              </div>
              <div className="hidden sm:flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-[0.18em] text-ink-tertiary">
                <span>1M</span>
                <span className="text-white">3M</span>
                <span>6M</span>
                <span>1Y</span>
                <span>ALL</span>
              </div>
            </div>

            <EquityCurve />

            {/* Bottom stats row */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-8 pt-8 border-t border-line">
              {[
                { k: "Best day", v: "+8.4%" },
                { k: "Worst day", v: "−3.1%" },
                { k: "Win rate", v: "64.8%" },
                { k: "Profit factor", v: "2.14" },
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

          {/* Right column: liquidity heatmap */}
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-80px" }}
            transition={{ duration: 0.8, ease, delay: 0.1 }}
            className="lg:col-span-4 surface rounded-3xl p-8 lg:p-10 flex flex-col"
          >
            <div className="mb-6">
              <div className="text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary mb-1.5">
                Liquidity heatmap
              </div>
              <div className="text-[16px] text-white font-medium">
                Order book depth
              </div>
            </div>
            <LiquidityHeatmap />
            <div className="mt-6 pt-6 border-t border-line flex items-center justify-between">
              <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-[0.18em] text-ink-tertiary">
                <span>BID</span>
                <div className="h-1.5 w-1.5 rounded-full bg-success" />
                <span>·</span>
                <div className="h-1.5 w-1.5 rounded-full bg-danger" />
                <span>ASK</span>
              </div>
              <span className="text-[10px] font-mono text-ink-tertiary">
                Live · NIFTY
              </span>
            </div>
          </motion.div>

          {/* Bottom row: execution flow timeline */}
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-80px" }}
            transition={{ duration: 0.8, ease, delay: 0.15 }}
            className="lg:col-span-7 surface rounded-3xl p-8 lg:p-10"
          >
            <div className="flex items-center justify-between mb-6">
              <div>
                <div className="text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary mb-1.5">
                  Execution flow · 24h
                </div>
                <div className="text-[16px] text-white font-medium">
                  Order velocity
                </div>
              </div>
              <div className="text-[11px] font-mono text-ink-tertiary">
                1,248 orders · 96% filled
              </div>
            </div>
            <ExecutionFlow />
          </motion.div>

          {/* Bottom right: AI decision trail */}
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-80px" }}
            transition={{ duration: 0.8, ease, delay: 0.2 }}
            className="lg:col-span-5 surface rounded-3xl p-8 lg:p-10"
          >
            <div className="mb-6">
              <div className="text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary mb-1.5">
                AI decision trail
              </div>
              <div className="text-[16px] text-white font-medium">
                Last hour
              </div>
            </div>
            <DecisionTrail />
          </motion.div>
        </div>
      </div>
    </section>
  );
}

function EquityCurve() {
  // Smooth synthetic equity curve
  const points = [
    0, 2, 4, 3, 6, 8, 7, 11, 14, 12, 16, 19, 17, 22, 24, 23, 28, 31, 30,
    35, 38, 36, 41, 44, 47, 45, 48,
  ];

  const w = 800;
  const h = 240;
  const max = Math.max(...points);
  const stepX = w / (points.length - 1);

  const path = points
    .map((p, i) => {
      const x = i * stepX;
      const y = h - (p / max) * (h - 30) - 15;
      return `${i === 0 ? "M" : "L"} ${x} ${y}`;
    })
    .join(" ");

  return (
    <div className="relative h-[240px]">
      <svg
        viewBox={`0 0 ${w} ${h}`}
        className="w-full h-full"
        preserveAspectRatio="none"
      >
        <defs>
          <linearGradient id="eq-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#00D4FF" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#00D4FF" stopOpacity="0" />
          </linearGradient>
          <linearGradient id="eq-line" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#00D4FF" />
            <stop offset="100%" stopColor="#00FF88" />
          </linearGradient>
        </defs>

        {/* Horizontal grid */}
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

        {/* Area */}
        <motion.path
          d={`${path} L ${w} ${h} L 0 ${h} Z`}
          fill="url(#eq-grad)"
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 1.5, ease }}
        />

        {/* Line */}
        <motion.path
          d={path}
          fill="none"
          stroke="url(#eq-line)"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          initial={{ pathLength: 0 }}
          whileInView={{ pathLength: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 2, ease }}
        />

        {/* Moving "now" pulse */}
        {(() => {
          const lastX = (points.length - 1) * stepX;
          const lastY = h - (points[points.length - 1] / max) * (h - 30) - 15;
          return (
            <>
              <motion.circle
                cx={lastX}
                cy={lastY}
                r="6"
                fill="#00FF88"
                initial={{ scale: 0 }}
                whileInView={{ scale: 1 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: 1.5, ease }}
              />
              <circle cx={lastX} cy={lastY} r="6" fill="#00FF88" opacity="0.4">
                <animate
                  attributeName="r"
                  values="6;14;6"
                  dur="2.4s"
                  repeatCount="indefinite"
                />
                <animate
                  attributeName="opacity"
                  values="0.5;0;0.5"
                  dur="2.4s"
                  repeatCount="indefinite"
                />
              </circle>
            </>
          );
        })()}
      </svg>
    </div>
  );
}

function LiquidityHeatmap() {
  // Bid (left, green) and ask (right, red) heatmap bars
  const levels = [
    { bid: 0.9, ask: 0.3 },
    { bid: 0.7, ask: 0.5 },
    { bid: 0.5, ask: 0.4 },
    { bid: 0.4, ask: 0.7 },
    { bid: 0.6, ask: 0.85 },
    { bid: 0.3, ask: 0.5 },
    { bid: 0.8, ask: 0.6 },
    { bid: 0.45, ask: 0.4 },
    { bid: 0.55, ask: 0.7 },
    { bid: 0.35, ask: 0.9 },
    { bid: 0.7, ask: 0.5 },
    { bid: 0.5, ask: 0.3 },
  ];

  return (
    <div className="flex-1 flex flex-col gap-1.5">
      {levels.map((l, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0, scaleX: 0 }}
          whileInView={{ opacity: 1, scaleX: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, delay: i * 0.04, ease }}
          className="flex items-center gap-2 h-5"
        >
          {/* Bid (left) */}
          <div className="flex-1 flex justify-end">
            <div
              className="h-full rounded-sm bg-success/60 origin-right"
              style={{ width: `${l.bid * 100}%` }}
            />
          </div>
          {/* Spread (center) */}
          <div className="w-px h-3 bg-white/20" />
          {/* Ask (right) */}
          <div className="flex-1">
            <div
              className="h-full rounded-sm bg-danger/60 origin-left"
              style={{ width: `${l.ask * 100}%` }}
            />
          </div>
        </motion.div>
      ))}
    </div>
  );
}

function ExecutionFlow() {
  // Generate a particle-blob density map
  const dots = Array.from({ length: 240 }, () => ({
    x: Math.random() * 100,
    y: Math.random() * 100,
    s: Math.random() * 2 + 0.5,
    o: Math.random() * 0.6 + 0.1,
    d: Math.random() * 3,
  }));

  return (
    <div className="relative h-[200px] rounded-xl overflow-hidden border border-line bg-[#070708]">
      <div className="absolute inset-0">
        {dots.map((d, i) => (
          <motion.div
            key={i}
            className="absolute rounded-full"
            style={{
              left: `${d.x}%`,
              top: `${d.y}%`,
              width: d.s,
              height: d.s,
              background: d.y > 60 ? "#00FF88" : d.y < 30 ? "#00D4FF" : "#A78BFA",
            }}
            initial={{ opacity: 0, scale: 0 }}
            whileInView={{ opacity: d.o, scale: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: d.d * 0.1, ease }}
          />
        ))}
      </div>

      {/* Scan line */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div
          className="absolute left-0 right-0 h-px bg-gradient-to-r from-transparent via-accent/60 to-transparent animate-scan-line"
          style={{ boxShadow: "0 0 12px rgba(0,212,255,0.6)" }}
        />
      </div>

      {/* Time markers */}
      <div className="absolute inset-x-0 bottom-0 flex justify-between px-3 py-1.5 text-[9px] font-mono uppercase tracking-[0.18em] text-ink-tertiary">
        <span>00:00</span>
        <span>06:00</span>
        <span>12:00</span>
        <span>18:00</span>
        <span>NOW</span>
      </div>
    </div>
  );
}

function DecisionTrail() {
  const trail = [
    { time: "12:48:02", action: "BUY", sym: "RELIANCE", qty: "120", color: "text-success" },
    { time: "12:46:18", action: "HEDGE", sym: "BANKNIFTY", qty: "1 LOT", color: "text-accent" },
    { time: "12:31:44", action: "REDUCE", sym: "TCS", qty: "−30%", color: "text-warning" },
    { time: "12:14:09", action: "SELL", sym: "HDFCBANK", qty: "85", color: "text-danger" },
    { time: "11:58:32", action: "BUY", sym: "INFY", qty: "210", color: "text-success" },
    { time: "11:42:11", action: "BUY", sym: "BHARTI", qty: "340", color: "text-success" },
  ];

  return (
    <div className="flex flex-col gap-3">
      {trail.map((t, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0, x: -8 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5, delay: i * 0.05, ease }}
          className="grid grid-cols-12 gap-2 items-center py-1.5 border-b border-line/50 last:border-0"
        >
          <span className="col-span-3 text-[10px] font-mono text-ink-tertiary nums">
            {t.time}
          </span>
          <span
            className={`col-span-2 text-[11px] font-mono uppercase tracking-[0.12em] ${t.color}`}
          >
            {t.action}
          </span>
          <span className="col-span-4 text-[12px] text-white">{t.sym}</span>
          <span className="col-span-3 text-right text-[12px] text-ink-secondary nums">
            {t.qty}
          </span>
        </motion.div>
      ))}
    </div>
  );
}
