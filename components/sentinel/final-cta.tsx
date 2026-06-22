"use client";

import { motion } from "framer-motion";
import { useMemo } from "react";

/**
 * Final CTA — Radical Redesign.
 *
 * Maximalist closing. Text "LET INTELLIGENCE COMPOUND" is broken
 * into individual words at different sizes and slight rotations.
 * Aurora animated gradient background. Larger, faster particles
 * with trail effects. Glassmorphic card around the CTA.
 */

const SPRING = { type: "spring" as const, stiffness: 100, damping: 18, bounce: 0 };

type Particle = { x: number; y: number; size: number; delay: number; duration: number };

function buildParticles(n: number): Particle[] {
  const out: Particle[] = [];
  let seed = 1234;
  const rand = () => {
    seed = (seed * 9301 + 49297) % 233280;
    return seed / 233280;
  };

  for (let i = 0; i < n; i++) {
    const angle = rand() * Math.PI * 2;
    const radius = 30 + rand() * 28;
    out.push({
      x: Math.cos(angle) * radius,
      y: Math.sin(angle) * radius,
      size: 1.5 + rand() * 3,
      delay: rand() * 3.5,
      duration: 4 + rand() * 3.5,
    });
  }
  return out;
}

export default function FinalCta() {
  const particles = useMemo(() => buildParticles(55), []);

  return (
    <section className="relative flex min-h-[100svh] items-center justify-center overflow-hidden bg-[#030303] px-5 py-24 text-center sm:py-32 aurora-bg">
      {/* Extra radial glow */}
      <div className="convergence-field" />

      {/* Larger, faster particle field */}
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
        {particles.map((p, i) => (
          <motion.span
            key={i}
            className="convergence-particle"
            initial={{ x: `${p.x}vw`, y: `${p.y}vh`, opacity: 0, scale: 1 }}
            animate={{
              x: "0vw",
              y: "0vh",
              opacity: [0, 1, 1, 0],
              scale: [1, 1.8, 1.8, 0.3],
            }}
            transition={{
              duration: p.duration,
              delay: p.delay,
              ease: "easeInOut",
              repeat: Infinity,
              repeatDelay: 1,
            }}
            style={{
              width: p.size,
              height: p.size,
              boxShadow: `0 0 ${p.size * 4}px rgba(0,229,255,0.6)`,
            }}
          />
        ))}
      </div>

      {/* Central core glow — bigger and brighter */}
      <div
        className="pointer-events-none absolute left-1/2 top-1/2 h-80 w-80 -translate-x-1/2 -translate-y-1/2 rounded-full"
        style={{
          background:
            "radial-gradient(circle, rgba(0,229,255,0.22) 0%, rgba(0,229,255,0.06) 35%, transparent 65%)",
          filter: "blur(15px)",
        }}
      />

      <div className="relative z-10 mx-auto max-w-4xl">
        <motion.span
          initial={{ opacity: 0, y: 10 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={SPRING}
          viewport={{ once: true }}
          className="font-mono text-[10px] uppercase tracking-[0.28em] text-[#00E5FF] block mb-8"
        >
          07 — Deploy
        </motion.span>

        {/* Words at different sizes and rotations */}
        <div className="flex flex-col items-center gap-0">
          <motion.span
            initial={{ opacity: 0, y: 30, rotate: -2 }}
            whileInView={{ opacity: 1, y: 0, rotate: -1 }}
            transition={{ ...SPRING, delay: 0.05 }}
            viewport={{ once: true }}
            className="font-editorial font-black text-white tracking-tight"
            style={{ fontSize: "clamp(2.5rem, 7vw, 7rem)", lineHeight: 1 }}
          >
            LET
          </motion.span>
          <motion.span
            initial={{ opacity: 0, y: 30, rotate: 1 }}
            whileInView={{ opacity: 1, y: 0, rotate: 0.5 }}
            transition={{ ...SPRING, delay: 0.12 }}
            viewport={{ once: true }}
            className="font-grotesk font-bold text-white text-glow-cyan tracking-tighter"
            style={{ fontSize: "clamp(4rem, 12vw, 12rem)", lineHeight: 0.85 }}
          >
            INTELLIGENCE
          </motion.span>
          <motion.span
            initial={{ opacity: 0, y: 30, rotate: -1 }}
            whileInView={{ opacity: 1, y: 0, rotate: 0 }}
            transition={{ ...SPRING, delay: 0.2 }}
            viewport={{ once: true }}
            className="font-editorial italic font-normal text-white/70 tracking-normal"
            style={{ fontSize: "clamp(2rem, 5vw, 5rem)", lineHeight: 1.1 }}
          >
            Compound.
          </motion.span>
        </div>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ ...SPRING, delay: 0.3 }}
          viewport={{ once: true }}
          className="mx-auto mt-8 max-w-md text-white/45 font-grotesk text-sm sm:text-base"
        >
          Deploy autonomous agents that never sleep.
        </motion.p>

        {/* CTA in a glassmorphic floating card */}
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ ...SPRING, delay: 0.4 }}
          viewport={{ once: true }}
          className="mt-12 inline-block"
        >
          <div
            className="glass-card p-6 sm:p-8 flex flex-col sm:flex-row items-center justify-center gap-4"
            style={{
              background: "rgba(10,10,12,0.60)",
              borderColor: "rgba(0,229,255,0.10)",
              boxShadow: "0 30px 80px -20px rgba(0,229,255,0.12), inset 0 1px 0 rgba(255,255,255,0.06)",
            }}
          >
            <a href="/signup" className="liquid-button liquid-button-primary">
              <span>Start Building</span>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path
                  d="M1 7h12M8 2l5 5-5 5"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </a>
            <a href="#agents" className="liquid-button">
              <span>Talk to the team</span>
            </a>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
