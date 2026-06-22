"use client";

import Link from "next/link";
import { motion, useScroll, useTransform } from "framer-motion";
import { useEffect, useState } from "react";

/**
 * Nav — Radical Redesign.
 *
 * Asymmetric nav bar: logo jammed to far-left edge, links clustered
 * right with irregular spacing. Background transitions from transparent
 * to a gradient accent strip on scroll. Active indicator is a glowing dot.
 */

const LINKS = [
  { label: "Intelligence", href: "#agents" },
  { label: "Markets", href: "#markets" },
  { label: "Strategies", href: "#strategies" },
  { label: "Trust", href: "#trust" },
];

export default function Nav() {
  const { scrollY } = useScroll();
  const opacity = useTransform(scrollY, [0, 120], [0, 1]);
  const y = useTransform(scrollY, [0, 120], [-14, 0]);
  const bgOpacity = useTransform(scrollY, [0, 200], [0, 0.92]);
  const [visible, setVisible] = useState(false);
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
    const unsub = opacity.on("change", (v) => setVisible(v > 0.05));
    return () => unsub();
  }, [opacity]);

  useEffect(() => {
    let cancelled = false;
    let unsubscribe: (() => void) | undefined;

    (async () => {
      try {
        const mod = await import("@/lib/supabase/client").catch(() => null);
        if (!mod) return;
        const supabase = mod.createClient();
        const { data } = await supabase.auth.getSession();
        if (!cancelled) setSignedIn(Boolean(data.session));
        const sub = supabase.auth.onAuthStateChange((_event, session) => {
          if (!cancelled) setSignedIn(Boolean(session));
        });
        unsubscribe = () => sub.data.subscription.unsubscribe();
      } catch {
        /* no-op */
      }
    })();

    return () => {
      cancelled = true;
      if (unsubscribe) unsubscribe();
    };
  }, []);

  return (
    <motion.header
      style={{ opacity, y }}
      className="fixed inset-x-0 top-0 z-50 px-0"
    >
      <motion.nav
        initial={false}
        animate={{ opacity: visible ? 1 : 0 }}
        transition={{ duration: 0.4 }}
        className="relative flex w-full items-center justify-between px-5 sm:px-8 lg:px-14 py-3 sm:py-4"
      >
        {/* Gradient background strip */}
        <motion.div
          className="absolute inset-0 pointer-events-none"
          style={{
            opacity: bgOpacity,
            background:
              "linear-gradient(180deg, rgba(3,3,3,0.95) 0%, rgba(3,3,3,0.85) 70%, transparent 100%)",
            backdropFilter: "blur(20px) saturate(180%)",
            WebkitBackdropFilter: "blur(20px) saturate(180%)",
          }}
        />
        {/* Thin accent line at bottom */}
        <motion.div
          className="absolute bottom-0 left-0 right-0 h-px pointer-events-none"
          style={{
            opacity: bgOpacity,
            background:
              "linear-gradient(90deg, transparent 0%, rgba(0,229,255,0.15) 30%, rgba(0,229,255,0.15) 70%, transparent 100%)",
          }}
        />

        {/* Logo — jammed left */}
        <Link href="/" className="relative z-10 flex items-center gap-2.5">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full rounded-full bg-[#00E5FF] opacity-60 animate-pulse-ring" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-[#00E5FF]" />
          </span>
          <span
            className="font-grotesk text-sm font-semibold tracking-[-0.02em] text-white"
          >
            POLYCOGNITIVE
          </span>
          <span className="hidden font-mono text-[9px] uppercase tracking-[0.3em] text-white/30 sm:inline">
            OS
          </span>
        </Link>

        {/* Links — irregular spacing, clustered right */}
        <div className="relative z-10 hidden items-center md:flex" style={{ gap: "clamp(16px, 3vw, 42px)" }}>
          {LINKS.map((l, i) => (
            <a
              key={l.label}
              href={l.href}
              className="group relative text-[13px] text-white/55 transition-colors duration-400 hover:text-white"
              style={{
                fontFamily: i % 2 === 0 ? "var(--font-grotesk)" : "var(--font-sans)",
                fontWeight: i === 0 ? 600 : 400,
                letterSpacing: i % 2 === 0 ? "-0.01em" : "0.02em",
              }}
            >
              {l.label}
              <span className="absolute -bottom-1 left-0 right-0 h-px bg-[#00E5FF] scale-x-0 group-hover:scale-x-100 transition-transform duration-500 origin-left" />
            </a>
          ))}
        </div>

        {/* Right cluster — sign in + CTA */}
        <div className="relative z-10 flex items-center gap-3 sm:gap-4">
          {signedIn ? (
            <Link
              href="/dashboard"
              className="hidden text-[13px] font-grotesk text-white/55 transition-colors duration-400 hover:text-white sm:inline"
            >
              Dashboard
            </Link>
          ) : (
            <Link
              href="/login"
              className="hidden text-[13px] text-white/55 transition-colors duration-400 hover:text-white sm:inline"
            >
              Sign in
            </Link>
          )}
          <Link
            href={signedIn ? "/dashboard" : "/signup"}
            className="liquid-button !py-2 !px-5 !text-[11px] !tracking-[0.1em] !font-semibold"
          >
            <span>{signedIn ? "Open App" : "Launch"}</span>
            <svg width="10" height="10" viewBox="0 0 14 14" fill="none">
              <path
                d="M1 7h12M8 2l5 5-5 5"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </Link>
        </div>
      </motion.nav>
    </motion.header>
  );
}
