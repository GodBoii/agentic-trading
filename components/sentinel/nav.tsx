"use client";

import Link from "next/link";
import { motion, useScroll, useTransform } from "framer-motion";
import { useEffect, useState } from "react";

/**
 * Sentinel Nav — a thin, fixed, glass nav at the very top of the page.
 * It reveals only after the user has scrolled a little (so the hero
 * stays clean and uncluttered). On mobile it collapses to a logo + CTA.
 *
 * The "Dashboard" link surfaces when the user is signed in, mirroring
 * the original landing/nav behaviour. Supabase is optional — if the
 * client can't be constructed we stay signed out and show Sign in.
 */

const SPRING = { type: "spring" as const, stiffness: 120, damping: 20, bounce: 0 };

const LINKS = [
  { label: "Intelligence", href: "#agents" },
  { label: "Markets",      href: "#markets" },
  { label: "Strategies",   href: "#strategies" },
  { label: "Trust",        href: "#trust" },
];

export default function Nav() {
  const { scrollY } = useScroll();
  const opacity = useTransform(scrollY, [0, 80], [0, 1]);
  const y = useTransform(scrollY, [0, 80], [-10, 0]);
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
      className="fixed inset-x-0 top-0 z-50 flex justify-center px-3 pt-3 sm:px-5 sm:pt-4"
    >
      <motion.nav
        initial={false}
        animate={{ opacity: visible ? 1 : 0 }}
        transition={{ duration: 0.3 }}
        className="glass-card flex w-full max-w-6xl items-center justify-between rounded-full px-4 py-2.5 sm:px-6 sm:py-3"
      >
        <Link href="/" className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full rounded-full bg-[#00E5FF] opacity-60 animate-pulse-ring" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-[#00E5FF]" />
          </span>
          <span className="font-display text-sm font-medium tracking-[-0.02em] text-white">
            SENTINEL
          </span>
          <span className="hidden font-mono text-[10px] uppercase tracking-[0.2em] text-white/40 sm:inline">
            / OS
          </span>
        </Link>

        <div className="hidden items-center gap-6 md:flex">
          {LINKS.map((l) => (
            <a
              key={l.label}
              href={l.href}
              className="text-sm text-white/70 transition-colors duration-300 hover:text-white"
            >
              {l.label}
            </a>
          ))}
        </div>

        <div className="flex items-center gap-2">
          {signedIn ? (
            <Link
              href="/dashboard"
              className="hidden text-sm text-white/70 transition-colors duration-300 hover:text-white sm:inline"
            >
              Dashboard
            </Link>
          ) : (
            <Link
              href="/login"
              className="hidden text-sm text-white/70 transition-colors duration-300 hover:text-white sm:inline"
            >
              Sign in
            </Link>
          )}
          <Link
            href={signedIn ? "/dashboard" : "/signup"}
            className="liquid-button !py-2 !px-4 !text-[12px]"
          >
            <span>{signedIn ? "Open App" : "Launch"}</span>
            <svg width="11" height="11" viewBox="0 0 14 14" fill="none">
              <path d="M1 7h12M8 2l5 5-5 5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </Link>
        </div>
      </motion.nav>
    </motion.header>
  );
}
