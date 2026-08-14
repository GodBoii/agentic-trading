"use client";

import Link from "next/link";
import { motion } from "framer-motion";

/**
 * Final CTA — quiet closing section.
 *
 * One heading, one line, two buttons. No particle fields,
 * no aurora gradients.
 */

const EASE = [0.16, 1, 0.3, 1] as const;

export default function FinalCta() {
  return (
    <section className="relative border-t border-white/[0.05] bg-[#030303] px-5 py-24 sm:px-8 sm:py-32">
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        whileInView={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, ease: EASE }}
        viewport={{ once: true, margin: "-15%" }}
        className="mx-auto max-w-6xl"
      >
        <h2 className="max-w-2xl font-grotesk text-3xl font-semibold tracking-[-0.03em] text-white sm:text-5xl">
          Put agents to work on your watchlist.
        </h2>
        <p className="mt-5 max-w-xl text-base leading-relaxed text-white/55">
          Create an account, connect Dhan, and let the system show you what
          it finds — you decide what trades.
        </p>
        <div className="mt-10 flex flex-col gap-4 sm:flex-row sm:items-center">
          <Link
            href="/signup"
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-white px-6 py-3 text-sm font-medium text-[#030303] transition-colors duration-300 hover:bg-white/90"
          >
            Get started
            <span aria-hidden>→</span>
          </Link>
          <Link
            href="/login"
            className="inline-flex items-center justify-center rounded-lg border border-white/[0.12] px-6 py-3 text-sm font-medium text-white/70 transition-colors duration-300 hover:border-white/25 hover:text-white"
          >
            Sign in
          </Link>
        </div>
      </motion.div>
    </section>
  );
}
