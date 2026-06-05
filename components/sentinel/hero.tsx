"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import Monolith from "@/components/gdb/Monolith";

const SPRING = { type: "spring" as const, stiffness: 120, damping: 20, bounce: 0 };

/**
 * GODBOY · Sentinel — opening section.
 *
 * The visitor's first impression: an iconic, monolithic, near-black void
 * with a slowly rotating celestial artifact (the "intelligence core") and
 * the brand wordmark carved into stone. No SaaS hero copy, no marketing
 * dashboards. Just presence. Then they scroll into the agentic product.
 *
 * The product is the agentic trading OS Sentinel — a constellation of
 * AI agents that research, signal, risk-manage, and execute.
 */
export default function Hero() {
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
    // Lightweight session check (no SSR-time coupling). If Supabase is
    // not configured the call just resolves null and we stay signed out.
    let cancelled = false;
    (async () => {
      try {
        const mod = await import("@/lib/supabase/client").catch(() => null);
        if (!mod) return;
        const supabase = mod.createClient();
        const { data } = await supabase.auth.getSession();
        if (!cancelled) setSignedIn(Boolean(data.session));
        const sub = supabase.auth.onAuthStateChange((_e, session) => {
          if (!cancelled) setSignedIn(Boolean(session));
        });
        return () => sub.data.subscription.unsubscribe();
      } catch {
        /* no-op */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section
      id="presence"
      className="relative w-full overflow-hidden void"
      style={{ minHeight: "100vh" }}
    >
      {/* Center crosshair (subtle, watch-dial) */}
      <div className="absolute inset-0 pointer-events-none" aria-hidden>
        <div
          className="absolute top-0 bottom-0 w-px"
          style={{ left: "50%", background: "rgba(255,255,255,0.04)" }}
        />
        <div
          className="absolute left-0 right-0 h-px"
          style={{ top: "50%", background: "rgba(255,255,255,0.04)" }}
        />
      </div>

      {/* Top-left brand mark */}
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1], delay: 0.2 }}
        className="absolute top-20 left-7 sm:top-24 sm:left-10 z-20 flex items-center gap-3"
      >
        <span
          className="inline-block w-1.5 h-1.5 rounded-full"
          style={{ background: "var(--gold)", boxShadow: "0 0 10px var(--gold-soft)" }}
        />
        <span className="godboy-mark">GODBOY · SENTINEL</span>
      </motion.div>

      {/* Top-right precision readouts */}
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1], delay: 0.35 }}
        className="absolute top-20 right-7 sm:top-24 sm:right-10 z-20 hidden sm:flex flex-col items-end gap-1"
      >
        <span className="godboy-mark">AUTONOMOUS · INTELLIGENCE · OS</span>
        <span className="godboy-mark" style={{ color: "rgba(255,255,255,0.20)" }}>SOVEREIGN · 001 / 999</span>
      </motion.div>

      {/* The Monolith — barely visible above the wordmark */}
      <motion.div
        initial={{ opacity: 0, scale: 0.94 }}
        animate={{ opacity: 0.9, scale: 1 }}
        transition={{ duration: 2.4, ease: [0.16, 1, 0.3, 1], delay: 0.1 }}
        className="absolute z-0 left-1/2 -translate-x-1/2 pointer-events-none"
        style={{ top: "10vh" }}
      >
        <Monolith size={320} />
      </motion.div>

      {/* THE WORDMARK — fills the lower 60–70% of the viewport */}
      <div
        className="relative z-10 mx-auto w-full px-2 flex flex-col items-center justify-center text-center"
        style={{ minHeight: "100vh", paddingTop: "22vh" }}
      >
        <motion.h1
          initial={{ opacity: 0, y: 80, filter: "blur(8px)" }}
          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          transition={{ duration: 1.8, ease: [0.16, 1, 0.3, 1], delay: 0.3 }}
          className="text-godboy-hero text-white select-none"
          style={{ textWrap: "balance" }}
        >
          GODBOY
        </motion.h1>

        {/* Sub-line — the product statement. Single sentence, italic serif. */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 1.4, ease: [0.16, 1, 0.3, 1], delay: 1.1 }}
          className="mt-8 sm:mt-12 flex flex-col items-center gap-4"
        >
          <p className="text-sentence-godboy text-white/75 italic">
            Build what outlives you.
          </p>
        </motion.div>

        {/* Sub-sub-line: the product essence (single mono line, restrained) */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 1.4, ease: [0.16, 1, 0.3, 1], delay: 1.5 }}
          className="mt-6 flex flex-col items-center gap-3"
        >
          <div className="flex items-center gap-3">
            <span className="w-6 h-px bg-white/20" />
            <span className="text-eyebrow-godboy text-white/45">
              Autonomous · Trading · Intelligence
            </span>
            <span className="w-6 h-px bg-white/20" />
          </div>
        </motion.div>

        {/* Product CTAs — the only place we surface actions. Thin, restrained. */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 1.4, ease: [0.16, 1, 0.3, 1], delay: 1.9 }}
          className="mt-14 sm:mt-20 flex flex-col sm:flex-row items-center gap-4 sm:gap-5"
        >
          <Link
            href={signedIn ? "/dashboard" : "/signup"}
            className="enter-button"
            aria-label={signedIn ? "Open dashboard" : "Launch Sentinel"}
          >
            <span>{signedIn ? "OPEN DASHBOARD" : "LAUNCH AGENT"}</span>
            <span className="arrow" aria-hidden>→</span>
          </Link>
          {!signedIn && (
            <Link
              href="/login"
              className="text-eyebrow-godboy text-white/45 hover:text-white transition-colors duration-500"
            >
              SIGN IN
            </Link>
          )}
        </motion.div>
      </div>

      {/* Bottom-left index */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1.4, ease: [0.16, 1, 0.3, 1], delay: 2.1 }}
        className="absolute bottom-7 left-7 sm:bottom-9 sm:left-10 z-20 hidden sm:flex items-center gap-3"
      >
        <span className="index-num">001 / 008</span>
        <span className="w-px h-3 bg-white/15" />
        <span className="godboy-mark" style={{ color: "rgba(255,255,255,0.30)" }}>PRESENCE</span>
      </motion.div>

      {/* Bottom-right scroll hint */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1.4, ease: [0.16, 1, 0.3, 1], delay: 2.1 }}
        className="absolute bottom-7 right-7 sm:bottom-9 sm:right-10 z-20 hidden sm:flex flex-col items-end gap-2"
      >
        <span className="godboy-mark" style={{ color: "rgba(255,255,255,0.30)" }}>SCROLL</span>
        <motion.div
          animate={{ y: [0, 6, 0] }}
          transition={{ duration: 3, ease: "easeInOut", repeat: Infinity }}
          className="w-px h-8 bg-gradient-to-b from-white/40 to-transparent"
        />
      </motion.div>
    </section>
  );
}
