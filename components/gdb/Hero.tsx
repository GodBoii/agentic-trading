"use client";

import { motion } from "framer-motion";
import Monolith from "./Monolith";

const ease = [0.16, 1, 0.3, 1] as const;

export default function Hero() {
  return (
    <section
      className="relative w-full overflow-hidden void"
      style={{ minHeight: "100vh" }}
    >
      {/* Top-left brand mark */}
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 1.4, ease, delay: 0.2 }}
        className="absolute top-7 left-7 sm:top-9 sm:left-10 z-20 flex items-center gap-3"
      >
        <span
          className="inline-block w-1.5 h-1.5 rounded-full"
          style={{ background: "var(--gold)", boxShadow: "0 0 10px var(--gold-soft)" }}
        />
        <span className="godboy-mark">GODBOY · MMXXVI</span>
      </motion.div>

      {/* Top-right precision readouts */}
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 1.4, ease, delay: 0.35 }}
        className="absolute top-7 right-7 sm:top-9 sm:right-10 z-20 hidden sm:flex flex-col items-end gap-1"
      >
        <span className="godboy-mark">EST. ANNO MMXXVI</span>
        <span className="godboy-mark" style={{ color: "rgba(255,255,255,0.20)" }}>SOVEREIGN · 001 / 999</span>
      </motion.div>

      {/* The Monolith — tucked behind the wordmark, barely visible */}
      <motion.div
        initial={{ opacity: 0, scale: 0.94 }}
        animate={{ opacity: 0.85, scale: 1 }}
        transition={{ duration: 2.6, ease, delay: 0.1 }}
        className="absolute z-0 left-1/2 -translate-x-1/2 pointer-events-none"
        style={{ top: "6vh" }}
      >
        <Monolith size={320} />
      </motion.div>

      {/* THE WORDMARK — takes ~70% of the viewport, centered */}
      <div
        className="relative z-10 mx-auto w-full px-2 flex flex-col items-center justify-center text-center"
        style={{ minHeight: "100vh", paddingTop: "18vh" }}
      >
        <motion.h1
          initial={{ opacity: 0, y: 80, filter: "blur(8px)" }}
          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          transition={{ duration: 1.8, ease, delay: 0.3 }}
          className="text-godboy-hero text-white select-none"
          style={{ textWrap: "balance" }}
        >
          GODBOY
        </motion.h1>

        {/* The single sentence. No CTA. No button. */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 1.4, ease, delay: 1.2 }}
          className="mt-10 sm:mt-14 flex flex-col items-center gap-3"
        >
          <div className="flex items-center gap-4">
            <span className="hidden sm:inline-block w-10 h-px bg-white/25" />
            <p className="text-sentence-godboy text-white/70 italic">
              Build what outlives you.
            </p>
            <span className="hidden sm:inline-block w-10 h-px bg-white/25" />
          </div>
        </motion.div>
      </div>

      {/* Bottom-right scroll hint */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1.4, ease, delay: 1.8 }}
        className="absolute bottom-7 right-7 sm:bottom-9 sm:right-10 z-20 hidden sm:flex flex-col items-end gap-2"
      >
        <span className="godboy-mark" style={{ color: "rgba(255,255,255,0.30)" }}>SCROLL</span>
        <motion.div
          animate={{ y: [0, 6, 0] }}
          transition={{ duration: 3, ease: "easeInOut", repeat: Infinity }}
          className="w-px h-8 bg-gradient-to-b from-white/40 to-transparent"
        />
      </motion.div>

      {/* Bottom-left index */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1.4, ease, delay: 1.8 }}
        className="absolute bottom-7 left-7 sm:bottom-9 sm:left-10 z-20 hidden sm:flex items-center gap-3"
      >
        <span className="index-num">001 / 005</span>
        <span className="w-px h-3 bg-white/15" />
        <span className="godboy-mark" style={{ color: "rgba(255,255,255,0.30)" }}>PRESENCE</span>
      </motion.div>
    </section>
  );
}
