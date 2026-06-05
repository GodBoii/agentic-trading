"use client";

import { motion } from "framer-motion";
import { ReactNode } from "react";

const ease = [0.16, 1, 0.3, 1] as const;

type CommandProps = {
  index: string;
  total: string;
  tag: string;
  word: string;
  caption: string;
  /** Where the word sits — for variety between sections */
  align?: "center" | "left";
  /** Show a tiny symbol next to the index (gold dot) */
  accentDot?: boolean;
  /** Optional decorative element */
  ornament?: ReactNode;
};

export default function Command({
  index,
  total,
  tag,
  word,
  caption,
  align = "center",
  accentDot = false,
  ornament,
}: CommandProps) {
  return (
    <section
      className="relative w-full overflow-hidden void"
      style={{ minHeight: "100vh" }}
    >
      {/* Top meta line */}
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, amount: 0.3 }}
        transition={{ duration: 1, ease, delay: 0.1 }}
        className="absolute top-7 left-7 sm:top-9 sm:left-10 z-20 flex items-center gap-3"
      >
        {accentDot && (
          <span
            className="inline-block w-1.5 h-1.5 rounded-full"
            style={{ background: "var(--gold)", boxShadow: "0 0 10px var(--gold-soft)" }}
          />
        )}
        <span className="index-num">{index} / {total}</span>
        <span className="w-px h-3 bg-white/15" />
        <span className="godboy-mark">{tag}</span>
      </motion.div>

      {/* Bottom meta line */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, amount: 0.3 }}
        transition={{ duration: 1, ease, delay: 0.2 }}
        className="absolute bottom-7 left-7 right-7 sm:bottom-9 sm:left-10 sm:right-10 z-20 flex items-center justify-between"
      >
        <span className="godboy-mark" style={{ color: "rgba(255,255,255,0.30)" }}>GODBOY</span>
        <span className="godboy-mark hidden sm:inline-block" style={{ color: "rgba(255,255,255,0.30)" }}>
          {caption.toUpperCase().slice(0, 28)}
        </span>
      </motion.div>

      {/* The word — commanded to the center of the screen */}
      <div
        className={`relative z-10 mx-auto max-w-[100vw] px-2 flex flex-col items-center justify-center ${
          align === "left" ? "sm:items-start sm:pl-12" : ""
        }`}
        style={{ minHeight: "100vh" }}
      >
        <motion.div
          initial={{ opacity: 0, y: 80, filter: "blur(8px)" }}
          whileInView={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          viewport={{ once: true, amount: 0.4 }}
          transition={{ duration: 1.4, ease }}
          className="w-full"
        >
          <h2 className="text-command text-center sm:text-left text-white">
            {word}
          </h2>
        </motion.div>

        {/* Small caption — the commandment */}
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.4 }}
          transition={{ duration: 1.2, ease, delay: 0.35 }}
          className="mt-12 sm:mt-16 flex items-center gap-5"
        >
          <span className="hidden sm:inline-block w-10 h-px bg-white/25" />
          <p className="text-sentence-godboy italic text-white/65 text-center sm:text-left">
            {caption}
          </p>
        </motion.div>

        {ornament && (
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.4 }}
            transition={{ duration: 1.2, ease, delay: 0.55 }}
            className="mt-20 sm:mt-28"
          >
            {ornament}
          </motion.div>
        )}
      </div>
    </section>
  );
}
