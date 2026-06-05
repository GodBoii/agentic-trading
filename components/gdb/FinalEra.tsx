"use client";

import { motion } from "framer-motion";
import Monolith from "./Monolith";

const ease = [0.16, 1, 0.3, 1] as const;

export default function FinalEra() {
  return (
    <section
      className="relative w-full overflow-hidden void"
      style={{ minHeight: "100vh" }}
    >
      {/* Top meta */}
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, amount: 0.3 }}
        transition={{ duration: 1, ease, delay: 0.1 }}
        className="absolute top-7 left-7 right-7 sm:top-9 sm:left-10 sm:right-10 z-20 flex items-center justify-between"
      >
        <div className="flex items-center gap-3">
          <span
            className="inline-block w-1.5 h-1.5 rounded-full"
            style={{
              background: "var(--gold)",
              boxShadow: "0 0 14px var(--gold-soft)",
            }}
          />
          <span className="godboy-mark">GODBOY</span>
        </div>
        <span className="index-num hidden sm:inline-block">006 / 005</span>
      </motion.div>

      {/* The reassembled Monolith — sits behind/above the wordmark as a faint presence */}
      <motion.div
        initial={{ opacity: 0, scale: 0.92 }}
        whileInView={{ opacity: 0.7, scale: 1 }}
        viewport={{ once: true, amount: 0.2 }}
        transition={{ duration: 2.4, ease }}
        className="absolute left-1/2 -translate-x-1/2 z-0 pointer-events-none"
        style={{ top: "10vh" }}
      >
        <Monolith size={420} />
      </motion.div>

      {/* The final wordmark — centered, centered, centered */}
      <div
        className="relative z-10 mx-auto max-w-[100vw] px-2 flex flex-col items-center justify-center text-center"
        style={{ minHeight: "100vh" }}
      >
        <motion.h2
          initial={{ opacity: 0, y: 70, filter: "blur(8px)" }}
          whileInView={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          viewport={{ once: true, amount: 0.4 }}
          transition={{ duration: 1.6, ease }}
          className="text-command text-white"
          style={{ textWrap: "balance" }}
        >
          CREATE
          <br />
          <span className="text-gold-soft">YOUR ERA</span>
        </motion.h2>

        {/* Single line beneath */}
        <motion.p
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.4 }}
          transition={{ duration: 1.2, ease, delay: 0.45 }}
          className="mt-10 sm:mt-14 text-sentence-godboy italic text-white/55"
        >
          The fragments are whole. The object is you.
        </motion.p>

        {/* ENTER — thin white border, no fill, no radius */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.4 }}
          transition={{ duration: 1.4, ease, delay: 0.7 }}
          className="mt-16 sm:mt-20"
        >
          <button type="button" className="enter-button" aria-label="Enter GODBOY">
            <span>ENTER</span>
            <span className="arrow" aria-hidden>→</span>
          </button>
        </motion.div>

        {/* Tiny footer note */}
        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true, amount: 0.4 }}
          transition={{ duration: 1.4, ease, delay: 1.1 }}
          className="mt-16 sm:mt-24 flex flex-col items-center gap-2"
        >
          <div className="flex items-center gap-3">
            <span className="w-10 h-px bg-white/15" />
            <span className="godboy-mark" style={{ color: "rgba(255,255,255,0.30)" }}>SOVEREIGN</span>
            <span className="w-10 h-px bg-white/15" />
          </div>
          <span className="godboy-mark" style={{ color: "rgba(255,255,255,0.18)" }}>
            © MMXXVI · ALL TIME RESERVED
          </span>
        </motion.div>
      </div>
    </section>
  );
}
