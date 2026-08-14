"use client";

import { motion } from "framer-motion";

/**
 * Platform — what the system actually does.
 *
 * A calm 2×2 grid describing the real services in the stack.
 * No fake telemetry, no chaos grid, no ghost numbers.
 */

const EASE = [0.16, 1, 0.3, 1] as const;

const MODULES = [
  {
    num: "01",
    name: "Universe Scanner",
    description:
      "Screens the NSE universe and builds a focused watchlist of instruments worth watching each session.",
  },
  {
    num: "02",
    name: "Market Data Gateway",
    description:
      "Streams live quotes and market depth through your broker connection so agents always work from current data.",
  },
  {
    num: "03",
    name: "Signal Engine",
    description:
      "Evaluates technical indicators across the watchlist and flags intraday setups as they form.",
  },
  {
    num: "04",
    name: "AI Trading Agents",
    description:
      "Reason over every signal, size positions within your risk bounds, and execute through Dhan — each step logged and explainable.",
  },
];

export default function AgentNetwork() {
  return (
    <section id="platform" className="relative border-t border-white/[0.05] bg-[#030303] px-5 py-24 sm:px-8 sm:py-32">
      <div className="mx-auto max-w-6xl">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: EASE }}
          viewport={{ once: true, margin: "-15%" }}
          className="max-w-2xl"
        >
          <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-[#00E5FF]">
            The platform
          </p>
          <h2 className="mt-5 font-grotesk text-3xl font-semibold tracking-[-0.03em] text-white sm:text-5xl">
            Four services, one pipeline.
          </h2>
          <p className="mt-5 text-base leading-relaxed text-white/55">
            Each part of the system does one job well. Together they take a
            market session from scan to supervised execution.
          </p>
        </motion.div>

        <div className="mt-14 grid gap-px overflow-hidden rounded-2xl border border-white/[0.06] bg-white/[0.06] sm:grid-cols-2">
          {MODULES.map((m, i) => (
            <motion.article
              key={m.num}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, ease: EASE, delay: i * 0.06 }}
              viewport={{ once: true, margin: "-10%" }}
              className="bg-[#050505] p-7 sm:p-9"
            >
              <span className="font-mono text-[11px] tracking-[0.2em] text-white/30">
                {m.num}
              </span>
              <h3 className="mt-4 font-grotesk text-xl font-semibold tracking-[-0.02em] text-white">
                {m.name}
              </h3>
              <p className="mt-3 text-sm leading-relaxed text-white/50">
                {m.description}
              </p>
            </motion.article>
          ))}
        </div>
      </div>
    </section>
  );
}
