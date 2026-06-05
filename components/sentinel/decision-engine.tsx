"use client";

import { motion } from "framer-motion";
import { useEffect, useState } from "react";

/**
 * Decision Engine — Section 5.
 *
 * A terminal-inspired glass panel on the right shows the live reasoning
 * feed. Lines continuously animate upward, infinite loop.
 *
 * The left side has a massive editorial headline + a few "live stats".
 */

const SPRING = { type: "spring" as const, stiffness: 120, damping: 20, bounce: 0 };

type FeedLine = {
  time: string;
  message: string;
  confidence: string;
  action: string;
  status: "Completed" | "Monitoring" | "Queued";
};

const FEED: FeedLine[] = [
  { time: "09:34:12", message: "Volatility spike detected.",                    confidence: "91.4%", action: "Reduce exposure by 12%",     status: "Completed"  },
  { time: "09:34:18", message: "News sentiment diverges from price action.",   confidence: "88.7%", action: "Hold execution window",       status: "Monitoring" },
  { time: "09:34:26", message: "Liquidity river thinning near resistance.",    confidence: "93.2%", action: "Route passive orders",        status: "Completed"  },
  { time: "09:34:31", message: "Correlation cluster expanding.",               confidence: "89.9%", action: "Rebalance hedge sleeve",      status: "Completed"  },
  { time: "09:34:44", message: "Macro impulse confirms risk budget.",          confidence: "94.1%", action: "Increase allocation by 4%",   status: "Queued"     },
  { time: "09:34:52", message: "Execution trail shows low slippage.",          confidence: "97.8%", action: "Continue agent routing",      status: "Completed"  },
  { time: "09:35:01", message: "Skew compression across mega caps.",           confidence: "86.5%", action: "Tilt toward upside convexity",status: "Monitoring" },
  { time: "09:35:09", message: "FX impulse confirms risk-on continuation.",    confidence: "92.1%", action: "Scale into long bias",        status: "Completed"  },
  { time: "09:35:14", message: "ETF flow imbalance widening.",                 confidence: "90.6%", action: "Front-run institutional",     status: "Queued"     },
  { time: "09:35:22", message: "Volatility surface flattening.",               confidence: "88.3%", action: "Tighten risk per unit",       status: "Completed"  },
];

function statusTone(s: FeedLine["status"]) {
  if (s === "Completed")  return "text-[#00FF9D]";
  if (s === "Monitoring") return "text-[#FFB800]";
  return "text-[#00E5FF]";
}

function FeedRow({ line, index }: { line: FeedLine; index: number }) {
  return (
    <div className="terminal-line font-mono text-[11px] sm:text-xs">
      <div className="flex items-center gap-2 text-white/35">
        <span>[{line.time}]</span>
        <span className="h-1 w-1 rounded-full bg-white/20" />
        <span className="text-[10px] uppercase tracking-[0.18em]">SENTINEL · REASON</span>
      </div>
      <p className="mt-2 text-[13px] font-sans text-white/90 sm:text-sm">{line.message}</p>
      <div className="mt-3 grid grid-cols-1 gap-1.5 text-white/55 sm:grid-cols-3 sm:gap-3">
        <span>
          Confidence:{" "}
          <b className="text-[#00FF9D]">{line.confidence}</b>
        </span>
        <span className="truncate">
          Action: <b className="text-white">{line.action}</b>
        </span>
        <span>
          Execution:{" "}
          <b className={statusTone(line.status)}>{line.status}</b>
        </span>
      </div>
    </div>
  );
}

function LiveStats() {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((v) => v + 1), 3000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="mt-10 grid grid-cols-3 gap-px overflow-hidden rounded-2xl border border-white/[0.07] bg-white/[0.07]">
      {[
        ["Decisions / sec",  (4 + (tick % 3)).toString()],
        ["Avg Latency",      `${(11 + (tick % 4) * 0.4).toFixed(1)}ms`],
        ["Active Threads",   "1,284"],
      ].map(([label, value]) => (
        <div key={label} className="bg-[#030303]/90 p-4">
          <div className="font-mono text-[9px] uppercase tracking-[0.2em] text-white/40">{label}</div>
          <motion.div
            key={`${label}-${value}`}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            className="nums mt-1.5 font-mono text-lg text-[#F8F8F8] sm:text-2xl"
          >
            {value}
          </motion.div>
        </div>
      ))}
    </div>
  );
}

export default function DecisionEngine() {
  return (
    <section className="relative bg-[#030303] px-5 py-24 sm:px-8 sm:py-32">
      <div className="mx-auto grid max-w-6xl gap-12 lg:grid-cols-[0.85fr_1.15fr] lg:gap-16">
        <div>
          <motion.span
            initial={{ opacity: 0, y: 10 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={SPRING}
            viewport={{ once: true }}
            className="font-mono text-[10px] uppercase tracking-[0.24em] text-[#00E5FF]"
          >
            05 — Decision engine
          </motion.span>
          <motion.h2
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ ...SPRING, delay: 0.1 }}
            viewport={{ once: true }}
            className="mt-4 text-4xl font-medium tracking-[-0.04em] text-white sm:text-6xl lg:text-7xl"
          >
            Reasoning,<br />not reacting.
          </motion.h2>
          <motion.p
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ ...SPRING, delay: 0.2 }}
            viewport={{ once: true }}
            className="mt-5 max-w-md text-white/55"
          >
            Every action is grounded in a chain of evidence. Every confidence
            number is auditable. Every execution is explainable.
          </motion.p>
          <LiveStats />
        </div>

        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ ...SPRING, delay: 0.2 }}
          viewport={{ once: true, margin: "-15%" }}
          className="terminal-panel relative h-[520px] overflow-hidden sm:h-[600px]"
        >
          <div className="sticky top-0 z-10 flex items-center justify-between border-b border-white/[0.06] bg-[#060608]/85 px-5 py-3 backdrop-blur-md">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-[#FF5B5B]" />
              <span className="h-2 w-2 rounded-full bg-[#FFB800]" />
              <span className="h-2 w-2 rounded-full bg-[#00FF9D]" />
              <span className="ml-2 font-mono text-[10px] uppercase tracking-[0.2em] text-white/40">
                sentinel.terminal
              </span>
            </div>
            <span className="hidden font-mono text-[10px] uppercase tracking-[0.2em] text-white/40 sm:flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-[#00FF9D] shadow-[0_0_8px_#00FF9D] animate-pulse-soft" />
              Streaming
            </span>
          </div>

          <div className="relative h-[calc(100%-44px)] overflow-hidden">
            <motion.div
              animate={{ y: ["0%", "-50%"] }}
              transition={{ duration: 30, ease: "linear", repeat: Infinity }}
              className="absolute inset-x-0 top-0 space-y-3 p-4 sm:p-5"
            >
              {[...FEED, ...FEED].map((line, i) => (
                <FeedRow key={`${line.time}-${i}`} line={line} index={i} />
              ))}
            </motion.div>

            {/* Top + bottom fades so the loop blends smoothly */}
            <div className="pointer-events-none absolute inset-x-0 top-0 h-20 bg-gradient-to-b from-[#060608] to-transparent" />
            <div className="pointer-events-none absolute inset-x-0 bottom-0 h-20 bg-gradient-to-t from-[#060608] to-transparent" />
          </div>
        </motion.div>
      </div>
    </section>
  );
}
