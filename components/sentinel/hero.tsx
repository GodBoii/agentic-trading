"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { useEffect, useState } from "react";

/**
 * Hero — professional, single-column intro.
 *
 * One clear headline, one honest paragraph, two actions.
 * No scramble text, no mouse parallax, no floating artifacts —
 * just typography and a restrained fade-in.
 */

const EASE = [0.16, 1, 0.3, 1] as const;

function FadeUp({
  children,
  delay = 0,
  className,
}: {
  children: React.ReactNode;
  delay?: number;
  className?: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.8, ease: EASE, delay }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

export default function Hero() {
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
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
    <section className="relative w-full bg-[#030303]">
      {/* Static, subtle top glow — not animated */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-[480px]"
        style={{
          background:
            "radial-gradient(ellipse 720px 420px at 50% -8%, rgba(0,229,255,0.07) 0%, transparent 70%)",
        }}
      />

      <div className="relative mx-auto flex min-h-[100svh] w-full max-w-6xl flex-col justify-center px-5 pb-20 pt-32 sm:px-8">
        <FadeUp delay={0}>
          <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-[#00E5FF]">
            AI trading agents · Dhan broker integration
          </p>
        </FadeUp>

        <FadeUp delay={0.1}>
          <h1 className="mt-6 max-w-3xl font-grotesk text-4xl font-semibold leading-[1.05] tracking-[-0.03em] text-white sm:text-6xl">
            Autonomous trading intelligence for Indian markets.
          </h1>
        </FadeUp>

        <FadeUp delay={0.2}>
          <p className="mt-6 max-w-xl text-base leading-relaxed text-white/55 sm:text-lg">
            PolyCognition connects to your Dhan broker, scans the NSE
            universe, and surfaces intraday opportunities — with reasoning
            you can read and risk limits you control.
          </p>
        </FadeUp>

        <FadeUp delay={0.3}>
          <div className="mt-10 flex flex-col gap-4 sm:flex-row sm:items-center">
            <Link
              href={signedIn ? "/dashboard" : "/signup"}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-white px-6 py-3 text-sm font-medium text-[#030303] transition-colors duration-300 hover:bg-white/90"
            >
              {signedIn ? "Open dashboard" : "Get started"}
              <span aria-hidden>→</span>
            </Link>
            {!signedIn && (
              <Link
                href="/login"
                className="inline-flex items-center justify-center rounded-lg border border-white/[0.12] px-6 py-3 text-sm font-medium text-white/70 transition-colors duration-300 hover:border-white/25 hover:text-white"
              >
                Sign in
              </Link>
            )}
          </div>
        </FadeUp>

        <FadeUp delay={0.45} className="mt-16">
          <p className="max-w-xl text-[12px] leading-relaxed text-white/30">
            Built for research and assisted execution. Markets carry risk —
            review every decision before capital is committed.
          </p>
        </FadeUp>
      </div>
    </section>
  );
}
