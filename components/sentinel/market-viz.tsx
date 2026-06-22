"use client";

import { motion, useScroll, useTransform, useMotionValue, useSpring } from "framer-motion";
import { useRef, useCallback } from "react";

/**
 * Market Visualization — Radical Redesign.
 *
 * Full-bleed canvas with no padding. The heading "HOW AN AI SEES MARKETS"
 * overlays on top at massive scale with mix-blend-mode: difference.
 * Mouse-reactive radial gradient glow follows cursor.
 * Tripled visual density — more rivers, trails, clouds.
 */

const SPRING = { type: "spring" as const, stiffness: 120, damping: 20, bounce: 0 };

const HEATMAP_CELLS = [
  { x: 5, y: 12, size: 22, hue: 0 },
  { x: 18, y: 28, size: 30, hue: 0.2 },
  { x: 35, y: 10, size: 18, hue: 0.6 },
  { x: 50, y: 32, size: 38, hue: 0.9 },
  { x: 8, y: 50, size: 28, hue: 0.3 },
  { x: 28, y: 56, size: 42, hue: 0.8 },
  { x: 48, y: 48, size: 26, hue: 0.1 },
  { x: 68, y: 54, size: 34, hue: 0.7 },
  { x: 15, y: 76, size: 36, hue: 0.4 },
  { x: 38, y: 82, size: 24, hue: 0.5 },
  { x: 58, y: 74, size: 30, hue: 0.2 },
  { x: 78, y: 84, size: 20, hue: 0.6 },
  // Extra cells for density
  { x: 72, y: 18, size: 26, hue: 0.35 },
  { x: 85, y: 38, size: 20, hue: 0.55 },
  { x: 90, y: 66, size: 24, hue: 0.15 },
  { x: 62, y: 22, size: 16, hue: 0.75 },
  { x: 42, y: 38, size: 20, hue: 0.45 },
  { x: 22, y: 42, size: 14, hue: 0.85 },
];

function heatColor(t: number, alpha = 0.45) {
  if (t < 0.5) {
    const k = t / 0.5;
    return `rgba(${Math.round(0 + k * 0)}, ${Math.round(229 + k * 26)}, ${Math.round(255 - k * 100)}, ${alpha})`;
  }
  const k = (t - 0.5) / 0.5;
  return `rgba(${Math.round(0 + k * 255)}, ${Math.round(255 - k * 200)}, ${Math.round(155 - k * 100)}, ${alpha})`;
}

const EXECUTION_TRAILS = [
  { top: "22%", left: "5%", width: "30%", delay: "0s", duration: "4.8s" },
  { top: "38%", left: "35%", width: "38%", delay: "1.2s", duration: "5.4s" },
  { top: "55%", left: "15%", width: "28%", delay: "0.6s", duration: "4.2s" },
  { top: "68%", left: "50%", width: "34%", delay: "1.8s", duration: "5.8s" },
  { top: "82%", left: "8%", width: "24%", delay: "2.4s", duration: "4.6s" },
  { top: "30%", left: "65%", width: "26%", delay: "0.3s", duration: "5.2s" },
  { top: "75%", left: "40%", width: "30%", delay: "1.5s", duration: "4.4s" },
  { top: "48%", left: "70%", width: "22%", delay: "2.0s", duration: "5.0s" },
];

export default function MarketViz() {
  const ref = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start end", "end start"],
  });
  const scale = useTransform(scrollYProgress, [0, 0.5, 1], [0.95, 1, 1.05]);
  const rotate = useTransform(scrollYProgress, [0, 1], [-0.5, 0.5]);

  const mouseX = useMotionValue(0.5);
  const mouseY = useMotionValue(0.5);
  const springMouseX = useSpring(mouseX, { stiffness: 40, damping: 15 });
  const springMouseY = useSpring(mouseY, { stiffness: 40, damping: 15 });

  const glowX = useTransform(springMouseX, [0, 1], ["0%", "100%"]);
  const glowY = useTransform(springMouseY, [0, 1], ["0%", "100%"]);

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!canvasRef.current) return;
      const rect = canvasRef.current.getBoundingClientRect();
      mouseX.set((e.clientX - rect.left) / rect.width);
      mouseY.set((e.clientY - rect.top) / rect.height);
    },
    [mouseX, mouseY]
  );

  return (
    <section id="markets" ref={ref} className="relative overflow-hidden bg-[#030303]">
      {/* Title overlaid on the viz with mix-blend-mode: difference */}
      <div className="relative z-20 px-5 pt-20 sm:px-8 sm:pt-28 lg:pt-36 pointer-events-none">
        <div className="mx-auto max-w-[1400px]">
          <motion.span
            initial={{ opacity: 0, y: 10 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={SPRING}
            viewport={{ once: true, margin: "-20%" }}
            className="font-mono text-[10px] uppercase tracking-[0.28em] text-[#00E5FF] block mb-4"
          >
            03 — Market visualization
          </motion.span>

          <motion.h2
            initial={{ opacity: 0, y: 40 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ ...SPRING, delay: 0.1 }}
            viewport={{ once: true, margin: "-20%" }}
            className="font-editorial font-bold tracking-[-0.04em] text-white"
            style={{
              fontSize: "clamp(3rem, 9vw, 10rem)",
              lineHeight: 0.88,
              mixBlendMode: "difference",
            }}
          >
            How an AI
            <br />
            <span className="font-grotesk" style={{ fontSize: "clamp(2rem, 6vw, 7rem)" }}>
              sees markets.
            </span>
          </motion.h2>
        </div>
      </div>

      {/* Full-bleed canvas — no side padding */}
      <motion.div
        ref={canvasRef}
        onMouseMove={handleMouseMove}
        className="market-canvas relative w-full -mt-16 sm:-mt-24"
        style={{
          scale,
          rotate,
          height: "80vh",
          minHeight: "600px",
          borderRadius: 0,
          border: "none",
          borderTop: "1px solid rgba(255,255,255,0.04)",
          borderBottom: "1px solid rgba(255,255,255,0.04)",
        }}
      >
        {/* Mouse-reactive radial glow */}
        <motion.div
          className="absolute pointer-events-none"
          style={{
            left: glowX,
            top: glowY,
            width: "500px",
            height: "500px",
            transform: "translate(-50%, -50%)",
            background:
              "radial-gradient(circle, rgba(0,229,255,0.12) 0%, rgba(0,229,255,0.03) 40%, transparent 70%)",
            filter: "blur(30px)",
          }}
        />

        {/* Triple volatility clouds */}
        <div className="vol-cloud cloud-a" />
        <div className="vol-cloud cloud-b" />
        <div
          className="vol-cloud"
          style={{
            position: "absolute",
            top: "55%",
            left: "45%",
            width: "28%",
            height: "28%",
            background: "radial-gradient(circle, rgba(139,92,246,0.20) 0%, transparent 60%)",
            filter: "blur(60px)",
            opacity: 0.55,
            animation: "cloud-drift 22s var(--ease-in-out) infinite",
            animationDelay: "-3s",
            borderRadius: "9999px",
            pointerEvents: "none",
          }}
        />

        {/* Heatmap cells */}
        <div className="absolute inset-0">
          {HEATMAP_CELLS.map((cell, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, scale: 0.6 }}
              whileInView={{ opacity: 1, scale: 1 }}
              transition={{ ...SPRING, delay: i * 0.03 }}
              viewport={{ once: true, margin: "-5%" }}
              className="absolute rounded-full"
              style={{
                left: `${cell.x}%`,
                top: `${cell.y}%`,
                width: `${cell.size * 1.2}%`,
                aspectRatio: "1",
                background: `radial-gradient(circle, ${heatColor(cell.hue, 0.5)} 0%, ${heatColor(cell.hue, 0.15)} 45%, transparent 70%)`,
                filter: "blur(6px)",
              }}
            />
          ))}
        </div>

        {/* Heatmap grid overlay */}
        <div className="heatmap" />

        {/* Triple liquidity rivers */}
        <div className="liquidity-river river-a" />
        <div className="liquidity-river river-b" />
        <div
          className="liquidity-river"
          style={{
            top: "45%",
            height: "60px",
            background:
              "linear-gradient(90deg, transparent 0%, rgba(139,92,246,0.0) 10%, rgba(139,92,246,0.30) 35%, rgba(139,92,246,0.40) 55%, rgba(139,92,246,0.25) 75%, transparent 100%)",
            filter: "blur(0.5px)",
            transform: "translateY(-50%)",
            animation: "river-flow 20s ease-in-out infinite",
            animationDelay: "-4s",
          }}
        />

        {/* Denser execution trails */}
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

        {/* Overlay annotations */}
        <div className="pointer-events-none absolute inset-0 z-10">
          <div className="absolute left-5 top-5 flex items-center gap-2 sm:left-8 sm:top-8">
            <span className="h-1.5 w-1.5 rounded-full bg-[#00FF9D] shadow-[0_0_10px_#00FF9D] animate-pulse-soft" />
            <span className="font-mono text-[9px] uppercase tracking-[0.22em] text-white/40">
              Live · Multi-asset · Real-time
            </span>
          </div>

          <div className="absolute right-5 top-5 hidden font-mono text-[9px] uppercase tracking-[0.22em] text-white/35 sm:flex items-center gap-3 sm:right-8 sm:top-8">
            <span className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-[#00E5FF]" />
              Equities
            </span>
            <span className="text-white/20">·</span>
            <span className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-[#00FF9D]" />
              Crypto
            </span>
            <span className="text-white/20">·</span>
            <span className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-[#8B5CF6]" />
              Derivatives
            </span>
            <span className="text-white/20">·</span>
            <span className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-[#FF5B5B]" />
              Pressure
            </span>
          </div>

          <div className="absolute bottom-5 left-5 right-5 flex items-end justify-between sm:bottom-8 sm:left-8 sm:right-8">
            <div className="font-mono text-[9px] uppercase tracking-[0.22em] text-white/30">
              Timestamp · <span className="text-white/50">T - 0.0001s</span>
            </div>
            <div className="hidden font-mono text-[9px] uppercase tracking-[0.22em] text-white/30 sm:flex items-center gap-3">
              <span>Frame 04 / 24</span>
              <span>·</span>
              <span>Render 1.2ms</span>
            </div>
          </div>
        </div>
      </motion.div>

      {/* Caption row — asymmetric sizes */}
      <div className="px-5 sm:px-8 lg:px-14 py-8 sm:py-12">
        <div className="mx-auto max-w-[1400px] grid grid-cols-2 sm:grid-cols-4 gap-4 sm:gap-6">
          {[
            { title: "Liquidity Rivers", sub: "Flow direction · Depth", size: "text-lg sm:text-2xl" },
            { title: "Volatility Clouds", sub: "Regime · Compression", size: "text-base sm:text-lg" },
            { title: "Pressure Heatmap", sub: "Crowd · Positioning", size: "text-xl sm:text-3xl" },
            { title: "Execution Trails", sub: "Routing · Slippage", size: "text-sm sm:text-base" },
          ].map(({ title, sub, size }) => (
            <motion.div
              key={title}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={SPRING}
              viewport={{ once: true }}
            >
              <div className={`font-grotesk font-semibold text-white tracking-tight ${size}`}>
                {title}
              </div>
              <div className="mt-1 font-mono text-[9px] uppercase tracking-[0.2em] text-white/35">
                {sub}
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
