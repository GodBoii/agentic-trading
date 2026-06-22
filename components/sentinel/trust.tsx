"use client";

import { motion, useScroll, useTransform } from "framer-motion";
import { useRef } from "react";

/**
 * Trust — Radical Redesign.
 *
 * Oversized editorial headline at ~18vw.
 * Metrics are scattered at seemingly random positions with
 * deliberately different visual sizes. A faint diagonal line
 * runs across the section. Network topology background preserved.
 */

const SPRING = { type: "spring" as const, stiffness: 100, damping: 18, bounce: 0 };

const METRICS = [
  {
    value: "$12.4B",
    label: "Simulated Volume",
    sub: "Across all strategies",
    size: "text-5xl sm:text-7xl lg:text-8xl",
    weight: "font-bold",
    position: { top: "12%", left: "5%", mobileOrder: 1 },
  },
  {
    value: "99.99%",
    label: "Uptime",
    sub: "Trailing 12 months",
    size: "text-2xl sm:text-3xl",
    weight: "font-medium",
    position: { top: "8%", right: "8%", mobileOrder: 2 },
  },
  {
    value: "12ms",
    label: "Average Latency",
    sub: "End-to-end execution",
    size: "text-3xl sm:text-5xl",
    weight: "font-bold",
    position: { top: "45%", left: "55%", mobileOrder: 3 },
  },
  {
    value: "AES-256",
    label: "Encryption",
    sub: "At rest and in flight",
    size: "text-xl sm:text-2xl",
    weight: "font-medium",
    position: { top: "55%", left: "8%", mobileOrder: 4 },
  },
  {
    value: "SOC 2",
    label: "Infrastructure",
    sub: "Type II certified",
    size: "text-lg sm:text-xl",
    weight: "font-normal",
    position: { top: "40%", right: "5%", mobileOrder: 5 },
  },
];

function TopologyBackground() {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start end", "end start"],
  });
  const y = useTransform(scrollYProgress, [0, 1], [0, -80]);
  const opacity = useTransform(scrollYProgress, [0, 0.5, 1], [0.2, 0.6, 0.2]);

  return (
    <motion.div
      ref={ref}
      style={{ y, opacity }}
      className="absolute inset-0 network-topology pointer-events-none"
    />
  );
}

export default function Trust() {
  return (
    <section
      id="trust"
      className="relative overflow-hidden bg-[#030303] px-5 py-20 sm:px-8 sm:py-28 lg:py-36"
    >
      <TopologyBackground />
      <div className="diagonal-line" style={{ top: "30%", left: "-10%" }} />

      {/* Radial wash */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_25%_35%,rgba(0,229,255,0.04),transparent_55%)] pointer-events-none" />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_75%_70%,rgba(0,255,157,0.03),transparent_50%)] pointer-events-none" />

      <div className="relative mx-auto max-w-[1400px]">
        <motion.span
          initial={{ opacity: 0, x: -20 }}
          whileInView={{ opacity: 1, x: 0 }}
          transition={SPRING}
          viewport={{ once: true }}
          className="font-mono text-[10px] uppercase tracking-[0.28em] text-[#00E5FF] block mb-6"
        >
          06 — Trust
        </motion.span>

        {/* Massive headline — takes up almost the full width */}
        <motion.h2
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ ...SPRING, delay: 0.1 }}
          viewport={{ once: true, margin: "-15%" }}
          className="font-editorial font-black text-white"
          style={{
            fontSize: "clamp(4rem, 14vw, 18rem)",
            lineHeight: 0.82,
            letterSpacing: "-0.05em",
          }}
        >
          Built for
          <br />
          <span className="font-grotesk font-bold" style={{ fontSize: "clamp(3rem, 10vw, 12rem)" }}>
            Scale.
          </span>
        </motion.h2>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ ...SPRING, delay: 0.2 }}
          viewport={{ once: true }}
          className="mt-8 max-w-lg text-white/45 font-grotesk text-sm sm:text-base leading-relaxed"
        >
          Engineered for capital that cannot afford to be wrong. Audited.
          Encrypted. Monitored around the clock by a system that never blinks.
        </motion.p>

        {/* Scattered metrics — desktop: absolute positioned, mobile: grid */}
        <div className="relative mt-16 sm:mt-24" style={{ minHeight: "clamp(400px, 50vh, 700px)" }}>
          {/* Desktop: scattered layout */}
          <div className="hidden md:block relative h-full" style={{ minHeight: "60vh" }}>
            {METRICS.map((m, i) => (
              <motion.div
                key={m.label}
                initial={{ opacity: 0, y: 30, scale: 0.9 }}
                whileInView={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ ...SPRING, delay: 0.08 * i }}
                viewport={{ once: true }}
                className="absolute group"
                style={{
                  ...m.position,
                }}
              >
                <p className="font-mono text-[9px] uppercase tracking-[0.22em] text-white/30 mb-2">
                  {m.label}
                </p>
                <p
                  className={`nums font-grotesk ${m.size} ${m.weight} text-white tracking-tight`}
                  style={{
                    textShadow:
                      i === 0
                        ? "0 0 60px rgba(0,229,255,0.15)"
                        : i === 2
                        ? "0 0 40px rgba(0,255,157,0.12)"
                        : "none",
                  }}
                >
                  {m.value}
                </p>
                <p className="mt-1.5 text-[11px] text-white/35 font-grotesk">{m.sub}</p>

                {/* Hover glow line */}
                <div className="absolute -bottom-2 left-0 right-0 h-px bg-gradient-to-r from-transparent via-[#00E5FF]/0 to-transparent transition-all duration-500 group-hover:via-[#00E5FF]/40" />
              </motion.div>
            ))}
          </div>

          {/* Mobile: structured grid */}
          <div className="md:hidden grid grid-cols-2 gap-6">
            {METRICS.map((m, i) => (
              <motion.div
                key={m.label}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                transition={{ ...SPRING, delay: 0.06 * i }}
                viewport={{ once: true }}
                className={i === 0 ? "col-span-2" : ""}
              >
                <p className="font-mono text-[9px] uppercase tracking-[0.2em] text-white/30 mb-1.5">
                  {m.label}
                </p>
                <p
                  className={`nums font-grotesk ${i === 0 ? "text-4xl font-bold" : "text-2xl font-medium"} text-white tracking-tight`}
                >
                  {m.value}
                </p>
                <p className="mt-1 text-[11px] text-white/35">{m.sub}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
