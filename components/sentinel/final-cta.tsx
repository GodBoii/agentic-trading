"use client";

import { motion } from "framer-motion";
import { useMemo } from "react";

/**
 * Final CTA — Section 7.
 *
 * "Let Intelligence Compound."  Particles converge into a central glow,
 * a single primary CTA sits at the visual focal point.
 *
 * The particle system is pure CSS: 40 absolutely-positioned dots whose
 * end-position is the center of the section. We stagger their delays so
 * the convergence feels organic, not synchronized.
 */

const SPRING = { type: "spring" as const, stiffness: 120, damping: 20, bounce: 0 };

type Particle = { x: number; y: number; size: number; delay: number; duration: number };

function buildParticles(n: number): Particle[] {
  // Deterministic pseudo-random so SSR matches client
  const out: Particle[] = [];
  let seed = 1234;
  const rand = () => {
    seed = (seed * 9301 + 49297) % 233280;
    return seed / 233280;
  };

  for (let i = 0; i < n; i++) {
    // Spawn somewhere on a ring around the center (45%..52% of section size)
    const angle = rand() * Math.PI * 2;
    const radius = 35 + rand() * 22; // vw %
    out.push({
      x: Math.cos(angle) * radius,
      y: Math.sin(angle) * radius,
      size: 1 + rand() * 2.2,
      delay: rand() * 4,
      duration: 5 + rand() * 4,
    });
  }
  return out;
}

export default function FinalCta() {
  const particles = useMemo(() => buildParticles(40), []);

  return (
    <section className="relative flex min-h-[100svh] items-center justify-center overflow-hidden bg-[#030303] px-5 py-24 text-center sm:py-32">
      {/* Radial glow at the convergence point */}
      <div className="convergence-field" />

      {/* Particle field */}
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
              scale: [1, 1.4, 1.4, 0.4],
            }}
            transition={{
              duration: p.duration,
              delay: p.delay,
              ease: "easeInOut",
              repeat: Infinity,
              repeatDelay: 1.5,
            }}
            style={{ width: p.size, height: p.size }}
          />
        ))}
      </div>

      {/* Central core glow */}
      <div
        className="pointer-events-none absolute left-1/2 top-1/2 h-64 w-64 -translate-x-1/2 -translate-y-1/2 rounded-full"
        style={{
          background: "radial-gradient(circle, rgba(0,229,255,0.18) 0%, rgba(0,229,255,0.04) 40%, transparent 70%)",
          filter: "blur(10px)",
        }}
      />

      <div className="relative z-10 mx-auto max-w-3xl">
        <motion.span
          initial={{ opacity: 0, y: 10 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={SPRING}
          viewport={{ once: true }}
          className="font-mono text-[10px] uppercase tracking-[0.24em] text-[#00E5FF]"
        >
          07 — Deploy
        </motion.span>

        <motion.h2
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ ...SPRING, delay: 0.1 }}
          viewport={{ once: true }}
          className="mt-5 text-[clamp(2.75rem,8vw,6.5rem)] font-medium leading-[0.92] tracking-[-0.05em] text-white"
        >
          Let Intelligence<br />Compound.
        </motion.h2>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ ...SPRING, delay: 0.2 }}
          viewport={{ once: true }}
          className="mx-auto mt-6 max-w-xl text-base text-white/60 sm:text-lg"
        >
          Deploy autonomous agents that never sleep.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 18 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ ...SPRING, delay: 0.32 }}
          viewport={{ once: true }}
          className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row"
        >
          <a href="/signup" className="liquid-button liquid-button-primary">
            <span>Start Building</span>
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M1 7h12M8 2l5 5-5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </a>
          <a href="#agents" className="liquid-button">
            <span>Talk to the team</span>
          </a>
        </motion.div>
      </div>
    </section>
  );
}
