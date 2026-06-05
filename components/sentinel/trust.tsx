"use client";

import { motion, useScroll, useTransform } from "framer-motion";
import { useRef } from "react";

/**
 * Trust — Section 6.
 *
 * Massive editorial headline "Built for Institutional Scale." with a
 * subtle animated network-topology background, then a row of 5 metrics.
 *
 * The metrics cells have hairline dividers and reveal in sequence.
 */

const SPRING = { type: "spring" as const, stiffness: 120, damping: 20, bounce: 0 };

const METRICS = [
  { value: "$12.4B",  label: "Simulated Volume",    sub: "Across all strategies"        },
  { value: "99.99%",  label: "Uptime",              sub: "Trailing 12 months"          },
  { value: "12ms",    label: "Average Latency",     sub: "End-to-end execution"         },
  { value: "AES-256", label: "Encryption",          sub: "At rest and in flight"        },
  { value: "SOC 2",   label: "Infrastructure",      sub: "Type II certified"            },
];

function TopologyBackground() {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start end", "end start"],
  });
  const y = useTransform(scrollYProgress, [0, 1], [0, -60]);
  const opacity = useTransform(scrollYProgress, [0, 0.5, 1], [0.3, 0.7, 0.3]);

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
    <section id="trust" className="relative overflow-hidden bg-[#030303] px-5 py-24 sm:px-8 sm:py-32 lg:py-40">
      <TopologyBackground />
      {/* Subtle radial wash on top of the topology for depth */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_40%,rgba(0,229,255,0.05),transparent_60%)] pointer-events-none" />

      <div className="relative mx-auto max-w-7xl">
        <motion.span
          initial={{ opacity: 0, y: 10 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={SPRING}
          viewport={{ once: true }}
          className="font-mono text-[10px] uppercase tracking-[0.24em] text-[#00E5FF]"
        >
          06 — Trust
        </motion.span>

        <motion.h2
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ ...SPRING, delay: 0.1 }}
          viewport={{ once: true, margin: "-15%" }}
          className="mt-6 text-[clamp(3rem,9vw,10rem)] font-medium leading-[0.88] tracking-[-0.05em] text-white"
        >
          Built for<br />Institutional Scale.
        </motion.h2>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ ...SPRING, delay: 0.2 }}
          viewport={{ once: true }}
          className="mt-8 max-w-xl text-white/55"
        >
          Engineered for capital that cannot afford to be wrong. Audited.
          Encrypted. Monitored around the clock by a system that never blinks.
        </motion.p>

        <div className="mt-16 sm:mt-20">
          <div className="grid gap-px overflow-hidden border border-white/[0.08] bg-white/[0.08] sm:grid-cols-2 md:grid-cols-5">
            {METRICS.map((m, i) => (
              <motion.div
                key={m.label}
                initial={{ opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                transition={{ ...SPRING, delay: 0.05 * i }}
                viewport={{ once: true }}
                className="group relative bg-[#030303]/92 p-5 sm:p-7"
              >
                <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[#00E5FF]/0 to-transparent transition-all duration-500 group-hover:via-[#00E5FF]/60" />
                <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-white/35">
                  {m.label}
                </p>
                <p className="nums mt-4 text-3xl font-medium tracking-tight text-white sm:text-4xl">
                  {m.value}
                </p>
                <p className="mt-2 text-[12px] text-white/45">{m.sub}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
