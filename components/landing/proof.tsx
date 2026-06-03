"use client";

import { motion, useInView } from "framer-motion";
import { useEffect, useRef, useState } from "react";

const ease = [0.16, 1, 0.3, 1] as const;

const PROOFS = [
  {
    value: 4.2,
    prefix: "$",
    suffix: "B",
    label: "Capital managed",
    sub: "Across 12,400 autonomous deployments",
  },
  {
    value: 99.4,
    suffix: "%",
    label: "Execution accuracy",
    sub: "Fill rate at optimal venue",
  },
  {
    value: 38,
    suffix: "ms",
    label: "Average latency",
    sub: "Signal to cleared order",
  },
  {
    value: 168,
    suffix: "h",
    label: "Autonomous runtime",
    sub: "Continuous operation per week",
  },
];

function useCountUp(target: number, duration = 1800, start = false) {
  const [val, setVal] = useState(0);
  useEffect(() => {
    if (!start) return;
    let raf = 0;
    const begin = performance.now();
    const tick = (now: number) => {
      const t = Math.min((now - begin) / duration, 1);
      const eased = 1 - Math.pow(1 - t, 3); // easeOutCubic
      setVal(target * eased);
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [start, target, duration]);
  return val;
}

function Counter({ value, start }: { value: number; start: boolean }) {
  const v = useCountUp(value, 1800, start);
  const display = value < 10 ? v.toFixed(1) : Math.round(v).toString();
  return <span className="nums">{display}</span>;
}

export default function Proof() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-100px" });

  return (
    <section
      ref={ref}
      className="relative bg-[#050505] py-32 overflow-hidden"
    >
      <div className="absolute inset-0 bg-grid-fine opacity-40 pointer-events-none" />

      <div className="relative mx-auto max-w-7xl px-6 lg:px-8">
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
              By the numbers
            </span>
          </div>
          <h2 className="font-display text-display-lg text-white text-balance">
            We don't do testimonials.
            <br />
            <span className="font-serif-italic text-ink-secondary">
              We do receipts.
            </span>
          </h2>
        </motion.div>

        {/* Grid of proof metrics */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-px bg-line rounded-3xl overflow-hidden border border-line">
          {PROOFS.map((p, i) => (
            <motion.div
              key={p.label}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-80px" }}
              transition={{ duration: 0.6, ease, delay: i * 0.08 }}
              className="bg-[#08080a] p-8 lg:p-10 flex flex-col gap-6 group"
            >
              {/* Subtle index */}
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-ink-tertiary">
                  Metric / 0{i + 1}
                </span>
                <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-ink-tertiary">
                  Live
                </span>
              </div>

              {/* Value */}
              <div className="font-display text-[64px] lg:text-[80px] text-white tracking-[-0.04em] leading-[0.9]">
                {p.prefix && <span className="text-ink-secondary">{p.prefix}</span>}
                <Counter value={p.value} start={inView} />
                <span className="text-accent">{p.suffix}</span>
              </div>

              {/* Label + sub */}
              <div className="flex flex-col gap-1.5 pt-6 border-t border-line">
                <span className="text-[14px] font-medium text-white tracking-[-0.01em]">
                  {p.label}
                </span>
                <span className="text-[12px] text-ink-tertiary leading-relaxed">
                  {p.sub}
                </span>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
