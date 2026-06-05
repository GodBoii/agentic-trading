"use client";

import { motion, useScroll, useTransform } from "framer-motion";
import { useRef } from "react";

/**
 * Market Visualization — Section 3.
 *
 * "How an AI sees markets."  We render four proprietary visual primitives:
 *   1. Liquidity rivers   — two horizontal flow lines that drift and breathe
 *   2. Volatility clouds  — two large blurred radial gradients
 *   3. Pressure heatmap   — a CSS grid that fades toward the edges
 *   4. Execution trails   — 4 short horizontal cyan trails that "shoot" left-to-right
 *
 * On scroll-into-view, each primitive fades and translates in.
 */

const SPRING = { type: "spring" as const, stiffness: 120, damping: 20, bounce: 0 };

const HEATMAP_CELLS = [
  { x: 8,  y: 18, size: 18, hue: 0   },
  { x: 28, y: 24, size: 26, hue: 0.2 },
  { x: 52, y: 14, size: 20, hue: 0.6 },
  { x: 72, y: 28, size: 32, hue: 0.9 },
  { x: 12, y: 46, size: 24, hue: 0.3 },
  { x: 38, y: 52, size: 36, hue: 0.8 },
  { x: 60, y: 44, size: 22, hue: 0.1 },
  { x: 82, y: 50, size: 28, hue: 0.7 },
  { x: 20, y: 72, size: 30, hue: 0.4 },
  { x: 46, y: 78, size: 22, hue: 0.5 },
  { x: 68, y: 70, size: 26, hue: 0.2 },
  { x: 86, y: 80, size: 18, hue: 0.6 },
];

function heatColor(t: number, alpha = 0.45) {
  // 0 → cyan, 0.5 → green (profit), 1 → red (loss)
  if (t < 0.5) {
    const k = t / 0.5;
    return `rgba(${Math.round(0 + k * 0)}, ${Math.round(229 + k * 26)}, ${Math.round(255 - k * 100)}, ${alpha})`;
  }
  const k = (t - 0.5) / 0.5;
  return `rgba(${Math.round(0 + k * 255)}, ${Math.round(255 - k * 200)}, ${Math.round(155 - k * 100)}, ${alpha})`;
}

const EXECUTION_TRAILS = [
  { top: "32%", left: "8%",  width: "26%", delay: "0s",   duration: "5.2s" },
  { top: "58%", left: "42%", width: "32%", delay: "1.4s", duration: "6.0s" },
  { top: "78%", left: "20%", width: "22%", delay: "0.7s", duration: "4.6s" },
  { top: "44%", left: "60%", width: "30%", delay: "2.1s", duration: "5.8s" },
];

export default function MarketViz() {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start end", "end start"],
  });
  const scale  = useTransform(scrollYProgress, [0, 0.5, 1], [0.96, 1, 1.04]);
  const rotate = useTransform(scrollYProgress, [0, 1], [-1, 1]);

  return (
    <section id="markets" ref={ref} className="relative overflow-hidden bg-[#030303] px-5 py-24 sm:px-8 sm:py-32">
      <div className="mx-auto max-w-7xl">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={SPRING}
          viewport={{ once: true, margin: "-20%" }}
          className="mb-10 sm:mb-14"
        >
          <span className="font-mono text-[10px] uppercase tracking-[0.24em] text-[#00E5FF]">
            03 — Market visualization
          </span>
          <h2 className="mt-4 max-w-3xl text-4xl font-medium tracking-[-0.04em] text-white sm:text-6xl lg:text-7xl">
            How an AI sees markets.
          </h2>
          <p className="mt-5 max-w-xl text-white/55">
            Not candlesticks. Not overlays. A proprietary visual language built for autonomous perception.
          </p>
        </motion.div>

        <motion.div
          style={{ scale, rotate }}
          className="market-canvas relative h-[58vh] min-h-[420px] w-full sm:h-[78vh] sm:min-h-[680px]"
        >
          {/* Volatility clouds */}
          <div className="vol-cloud cloud-a" />
          <div className="vol-cloud cloud-b" />

          {/* Heatmap cells */}
          <div className="absolute inset-0">
            {HEATMAP_CELLS.map((cell, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, scale: 0.8 }}
                whileInView={{ opacity: 1, scale: 1 }}
                transition={{ ...SPRING, delay: i * 0.04 }}
                viewport={{ once: true, margin: "-10%" }}
                className="absolute rounded-full"
                style={{
                  left: `${cell.x}%`,
                  top: `${cell.y}%`,
                  width: `${cell.size * 1.4}%`,
                  aspectRatio: "1",
                  background: `radial-gradient(circle, ${heatColor(cell.hue, 0.55)} 0%, ${heatColor(cell.hue, 0.18)} 45%, transparent 70%)`,
                  filter: "blur(8px)",
                }}
              />
            ))}
          </div>

          {/* Heatmap grid overlay */}
          <div className="heatmap" />

          {/* Liquidity rivers */}
          <div className="liquidity-river river-a" />
          <div className="liquidity-river river-b" />

          {/* Execution trails */}
          {EXECUTION_TRAILS.map((t, i) => (
            <div
              key={i}
              className="execution-trail"
              style={{
                top: t.top,
                left: t.left,
                width: t.width,
                animationDelay: t.delay,
                animationDuration: t.duration,
              }}
            />
          ))}

          {/* Overlay annotations — small, monospaced, in the corners */}
          <div className="pointer-events-none absolute inset-0">
            <div className="absolute left-5 top-5 flex items-center gap-2 sm:left-7 sm:top-7">
              <span className="h-1.5 w-1.5 rounded-full bg-[#00FF9D] shadow-[0_0_10px_#00FF9D] animate-pulse-soft" />
              <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-white/45">
                Live · Multi-asset
              </span>
            </div>

            <div className="absolute right-5 top-5 hidden font-mono text-[10px] uppercase tracking-[0.2em] text-white/40 sm:block">
              <div className="flex items-center gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-[#00E5FF]" />
                <span>Equities</span>
                <span className="text-white/30">·</span>
                <span className="h-1.5 w-1.5 rounded-full bg-[#00FF9D]" />
                <span>Crypto</span>
                <span className="text-white/30">·</span>
                <span className="h-1.5 w-1.5 rounded-full bg-[#FF5B5B]" />
                <span>Pressure</span>
              </div>
            </div>

            <div className="absolute bottom-5 left-5 right-5 flex items-end justify-between sm:bottom-7 sm:left-7 sm:right-7">
              <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-white/35">
                Timestamp ·{" "}
                <span className="text-white/55">T - 0.0001s</span>
              </div>
              <div className="hidden font-mono text-[10px] uppercase tracking-[0.2em] text-white/40 sm:flex items-center gap-3">
                <span>Frame 04 / 24</span>
                <span>·</span>
                <span>Render 1.2ms</span>
              </div>
            </div>
          </div>
        </motion.div>

        {/* Caption row */}
        <div className="mt-8 grid grid-cols-2 gap-4 sm:mt-10 sm:grid-cols-4 sm:gap-px sm:overflow-hidden sm:border sm:border-white/[0.07] sm:bg-white/[0.07]">
          {[
            ["Liquidity Rivers", "Flow direction · Depth"],
            ["Volatility Clouds", "Regime · Compression"],
            ["Pressure Heatmap", "Crowd · Positioning"],
            ["Execution Trails", "Routing · Slippage"],
          ].map(([title, sub]) => (
            <div key={title} className="rounded-2xl border border-white/[0.07] bg-[#030303]/90 p-4 sm:rounded-none sm:border-0">
              <div className="font-display text-base font-medium text-white">{title}</div>
              <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.18em] text-white/40">
                {sub}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
