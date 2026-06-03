"use client";

import Link from "next/link";
import { motion, useScroll, useTransform } from "framer-motion";
import { useRef } from "react";

const ease = [0.16, 1, 0.3, 1] as const;

export default function FinalCTA() {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start end", "end start"],
  });
  // Background animates slowly
  const rotate = useTransform(scrollYProgress, [0, 1], [0, 90]);
  const scale = useTransform(scrollYProgress, [0, 1], [1.05, 0.95]);

  return (
    <section
      ref={ref}
      className="relative bg-[#050505] py-40 lg:py-56 overflow-hidden"
    >
      {/* Slowed background animation */}
      <motion.div
        className="absolute inset-0 flex items-center justify-center pointer-events-none"
        style={{ rotate, scale }}
      >
        <div className="relative h-[800px] w-[800px]">
          {/* Concentric rings */}
          {[0, 1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="absolute inset-0 rounded-full border"
              style={{
                borderColor: `rgba(0, 212, 255, ${0.12 - i * 0.018})`,
                transform: `scale(${1 + i * 0.18})`,
              }}
            />
          ))}
          {/* Center core */}
          <div className="absolute inset-0 m-auto h-32 w-32 rounded-full bg-accent/10 blur-2xl" />
          <div className="absolute inset-0 m-auto h-16 w-16 rounded-full bg-accent/30 blur-md" />
          <div className="absolute inset-0 m-auto h-6 w-6 rounded-full bg-accent" />
        </div>
      </motion.div>

      {/* Radial vignette */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_0%,#050505_70%)] pointer-events-none" />

      <div className="relative mx-auto max-w-5xl px-6 lg:px-8 text-center">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.8, ease }}
          className="inline-flex items-center gap-2 mb-10"
        >
          <span className="h-px w-8 bg-accent" />
          <span className="text-[11px] font-mono uppercase tracking-[0.22em] text-accent">
            Deploy in 60 seconds
          </span>
          <span className="h-px w-8 bg-accent" />
        </motion.div>

        <motion.h2
          initial={{ opacity: 0, y: 32 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 1, ease }}
          className="font-display text-display-xl text-white text-balance"
        >
          Let intelligence
          <br />
          <span className="font-serif-italic text-ink-secondary">compound.</span>
        </motion.h2>

        <motion.p
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.9, ease, delay: 0.2 }}
          className="mt-10 text-[17px] text-ink-secondary max-w-2xl mx-auto leading-relaxed"
        >
          Deploy autonomous trading systems built for the next generation of
          markets. Connect your broker. Define your mandate. Walk away.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.9, ease, delay: 0.35 }}
          className="mt-14 flex flex-col sm:flex-row gap-3 justify-center"
        >
          <Link
            href="/signup"
            className="group relative inline-flex items-center justify-center gap-2 rounded-full bg-white px-7 py-4 text-[15px] font-medium text-black transition-all duration-500 ease-out-expo hover:shadow-[0_0_40px_rgba(255,255,255,0.22)] hover:-translate-y-0.5"
          >
            <span>Start Building</span>
            <span className="inline-block transition-transform duration-300 group-hover:translate-x-0.5">
              →
            </span>
          </Link>
          <Link
            href="/login"
            className="inline-flex items-center justify-center gap-2 rounded-full border border-white/15 bg-white/[0.04] backdrop-blur-sm px-7 py-4 text-[15px] font-medium text-white transition-all duration-500 ease-out-expo hover:bg-white/[0.08] hover:border-white/25"
          >
            <span>Talk to engineering</span>
          </Link>
        </motion.div>

        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true, margin: "-50px" }}
          transition={{ duration: 0.9, ease, delay: 0.5 }}
          className="mt-16 flex flex-col sm:flex-row items-center justify-center gap-x-8 gap-y-3 text-[12px] font-mono uppercase tracking-[0.18em] text-ink-tertiary"
        >
          <span className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-success animate-pulse-soft" />
            No credit card
          </span>
          <span>·</span>
          <span>SOC 2 audited</span>
          <span>·</span>
          <span>Cancel anytime</span>
        </motion.div>
      </div>
    </section>
  );
}
