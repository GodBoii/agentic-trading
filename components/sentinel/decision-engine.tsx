"use client";

import { motion } from "framer-motion";

/**
 * How it works — the honest pipeline, in three steps.
 *
 * Replaces the old fabricated "reasoning feed" terminal with a
 * straightforward description of the real flow.
 */

const EASE = [0.16, 1, 0.3, 1] as const;

const STEPS = [
  {
    num: "1",
    title: "Connect your broker",
    description:
      "Link your Dhan account once. Authentication and token renewal are handled for you in the background.",
  },
  {
    num: "2",
    title: "Agents scan and reason",
    description:
      "The scanner and signal engine watch the market while AI agents evaluate each opportunity and write down why it qualifies.",
  },
  {
    num: "3",
    title: "You stay in control",
    description:
      "Review signals, positions, and full trade history from the dashboard. Risk limits bound every automated action.",
  },
];

export default function DecisionEngine() {
  return (
    <section id="how-it-works" className="relative border-t border-white/[0.05] bg-[#030303] px-5 py-24 sm:px-8 sm:py-32">
      <div className="mx-auto max-w-6xl">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: EASE }}
          viewport={{ once: true, margin: "-15%" }}
          className="max-w-2xl"
        >
          <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-[#00E5FF]">
            How it works
          </p>
          <h2 className="mt-5 font-grotesk text-3xl font-semibold tracking-[-0.03em] text-white sm:text-5xl">
            From connection to execution in three steps.
          </h2>
        </motion.div>

        <ol className="mt-14 grid gap-10 sm:grid-cols-3 sm:gap-8">
          {STEPS.map((step, i) => (
            <motion.li
              key={step.num}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, ease: EASE, delay: i * 0.08 }}
              viewport={{ once: true, margin: "-10%" }}
              className="relative border-t border-white/[0.08] pt-6"
            >
              <span className="font-grotesk text-sm font-semibold text-[#00E5FF]">
                {step.num}
              </span>
              <h3 className="mt-3 font-grotesk text-lg font-semibold tracking-[-0.02em] text-white">
                {step.title}
              </h3>
              <p className="mt-3 text-sm leading-relaxed text-white/50">
                {step.description}
              </p>
            </motion.li>
          ))}
        </ol>
      </div>
    </section>
  );
}
