"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import BrandMark from "@/components/brand-mark";

/**
 * Nav — simple, professional header.
 *
 * Static bar with a subtle backdrop blur. No scroll-linked motion,
 * no animated indicators — just brand, section links, and auth actions.
 */

const LINKS = [
  { label: "Platform", href: "#platform" },
  { label: "How it works", href: "#how-it-works" },
];

export default function Nav() {
  const [signedIn, setSignedIn] = useState(false);

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
    <header className="fixed inset-x-0 top-0 z-50 border-b border-white/[0.06] bg-[#030303]/85 backdrop-blur-md">
      <nav className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between px-5 sm:px-8">
        {/* Brand */}
        <Link href="/" className="flex items-center gap-2.5" aria-label="PolyCognition home">
          <BrandMark className="h-7 w-7" priority />
          <span className="font-grotesk text-sm font-semibold tracking-[-0.01em] text-white">
            PolyCognition
          </span>
        </Link>

        {/* Section links */}
        <div className="hidden items-center gap-8 md:flex">
          {LINKS.map((l) => (
            <a
              key={l.label}
              href={l.href}
              className="text-[13px] text-white/55 transition-colors duration-300 hover:text-white"
            >
              {l.label}
            </a>
          ))}
        </div>

        {/* Auth actions */}
        <div className="flex items-center gap-3 sm:gap-5">
          {signedIn ? (
            <Link
              href="/dashboard"
              className="hidden text-[13px] text-white/55 transition-colors duration-300 hover:text-white sm:inline"
            >
              Dashboard
            </Link>
          ) : (
            <Link
              href="/login"
              className="hidden text-[13px] text-white/55 transition-colors duration-300 hover:text-white sm:inline"
            >
              Sign in
            </Link>
          )}
          <Link
            href={signedIn ? "/dashboard" : "/signup"}
            className="inline-flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-[13px] font-medium text-[#030303] transition-colors duration-300 hover:bg-white/90"
          >
            {signedIn ? "Open app" : "Get started"}
          </Link>
        </div>
      </nav>
    </header>
  );
}
