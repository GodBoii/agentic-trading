"use client";

import Link from "next/link";
import { motion, useMotionValue, useTransform, useSpring } from "framer-motion";
import { useEffect, useState, useCallback, useRef } from "react";
import Monolith from "@/components/gdb/Monolith";

/**
 * HERO — Radical Redesign.
 *
 * Split-screen asymmetric layout with:
 *   - Massive "SENTINEL" text scramble effect on load
 *   - Oversized background section number "001"
 *   - Floating data pills that react to mouse
 *   - Uneven vertical spacing (35vh top, 10vh bottom)
 *   - Mixed typography: editorial serif italic + mono + display
 *   - The Monolith still floats but now off-center
 */

const SCRAMBLE_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@#$%&*";

function useScrambleText(finalText: string, duration = 2000, delay = 500) {
  const [display, setDisplay] = useState("");
  const [done, setDone] = useState(false);

  useEffect(() => {
    let frame: number;
    let start: number | null = null;

    const timeout = setTimeout(() => {
      const animate = (timestamp: number) => {
        if (!start) start = timestamp;
        const elapsed = timestamp - start;
        const progress = Math.min(elapsed / duration, 1);

        let result = "";
        for (let i = 0; i < finalText.length; i++) {
          if (finalText[i] === " ") {
            result += " ";
          } else if (i / finalText.length < progress) {
            result += finalText[i];
          } else {
            result += SCRAMBLE_CHARS[Math.floor(Math.random() * SCRAMBLE_CHARS.length)];
          }
        }
        setDisplay(result);

        if (progress < 1) {
          frame = requestAnimationFrame(animate);
        } else {
          setDone(true);
        }
      };

      // Start with random chars
      setDisplay(
        finalText
          .split("")
          .map((c) => (c === " " ? " " : SCRAMBLE_CHARS[Math.floor(Math.random() * SCRAMBLE_CHARS.length)]))
          .join("")
      );
      frame = requestAnimationFrame(animate);
    }, delay);

    return () => {
      clearTimeout(timeout);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [finalText, duration, delay]);

  return { display, done };
}

const DATA_PILLS = [
  { label: "NIFTY 50", value: "24,841.20", change: "+1.24%", x: 12, y: 18 },
  { label: "BTC/USD", value: "64,201", change: "-0.83%", x: 78, y: 24 },
  { label: "VIX", value: "13.42", change: "-1.10%", x: 22, y: 72 },
  { label: "AGENTS", value: "4 ACTIVE", change: "LIVE", x: 82, y: 68 },
  { label: "LATENCY", value: "11ms", change: "P99", x: 55, y: 14 },
  { label: "SIGNALS", value: "18,400/s", change: "↑", x: 42, y: 82 },
];

export default function Hero() {
  const [signedIn, setSignedIn] = useState(false);
  const { display: heroText, done: scrambleDone } = useScrambleText("SENTINEL", 1800, 600);
  const mouseX = useMotionValue(0.5);
  const mouseY = useMotionValue(0.5);
  const containerRef = useRef<HTMLDivElement>(null);

  const springX = useSpring(mouseX, { stiffness: 50, damping: 20 });
  const springY = useSpring(mouseY, { stiffness: 50, damping: 20 });

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      mouseX.set((e.clientX - rect.left) / rect.width);
      mouseY.set((e.clientY - rect.top) / rect.height);
    },
    [mouseX, mouseY]
  );

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
    <section
      id="presence"
      ref={containerRef}
      onMouseMove={handleMouseMove}
      className="relative w-full overflow-hidden noise-texture"
      style={{ minHeight: "100vh", background: "#000" }}
    >
      {/* Oversized background "001" */}
      <div className="bg-number absolute -right-[5vw] top-[10vh] select-none" aria-hidden>
        001
      </div>

      {/* Subtle crosshair lines */}
      <div className="absolute inset-0 pointer-events-none" aria-hidden>
        <div
          className="absolute top-0 bottom-0 w-px"
          style={{ left: "38%", background: "rgba(255,255,255,0.03)" }}
        />
        <div
          className="absolute left-0 right-0 h-px"
          style={{ top: "55%", background: "rgba(255,255,255,0.03)" }}
        />
        {/* Diagonal accent */}
        <div className="diagonal-line" style={{ top: "20%", left: "-10%" }} />
      </div>

      {/* Top-left brand mark — tight to edge */}
      <motion.div
        initial={{ opacity: 0, x: -20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 1.4, ease: [0.16, 1, 0.3, 1], delay: 0.2 }}
        className="absolute top-8 left-5 sm:top-10 sm:left-8 z-20 flex items-center gap-3"
      >
        <span
          className="inline-block w-2 h-2 rounded-full"
          style={{ background: "var(--gold)", boxShadow: "0 0 14px var(--gold-soft)" }}
        />
        <span className="godboy-mark" style={{ letterSpacing: "0.5em" }}>
          GODBOY
        </span>
      </motion.div>

      {/* Top-right — stacked precision readouts */}
      <motion.div
        initial={{ opacity: 0, x: 20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 1.4, ease: [0.16, 1, 0.3, 1], delay: 0.4 }}
        className="absolute top-8 right-5 sm:top-10 sm:right-8 z-20 hidden sm:flex flex-col items-end gap-2"
      >
        <span className="font-mono text-[9px] tracking-[0.4em] text-white/25 uppercase">
          Autonomous · OS · v3.1
        </span>
        <span className="font-mono text-[9px] tracking-[0.4em] text-white/15 uppercase">
          Sovereign · 001 / ∞
        </span>
      </motion.div>

      {/* ── MAIN CONTENT: Asymmetric split ── */}
      <div
        className="relative z-10 mx-auto w-full max-w-[1600px] px-5 sm:px-8 lg:px-14"
        style={{ paddingTop: "32vh", paddingBottom: "8vh", minHeight: "100vh" }}
      >
        <div className="grid lg:grid-cols-[1.4fr_1fr] gap-8 lg:gap-4 items-end">
          {/* Left: Massive scramble title */}
          <div>
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 1, ease: [0.16, 1, 0.3, 1], delay: 0.3 }}
              className="mb-6"
            >
              <span className="font-editorial text-[clamp(1rem,1.8vw,1.4rem)] italic text-white/50 tracking-wide">
                The intelligence that never sleeps
              </span>
            </motion.div>

            <motion.h1
              initial={{ opacity: 0, y: 80, filter: "blur(12px)" }}
              animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
              transition={{ duration: 2, ease: [0.16, 1, 0.3, 1], delay: 0.5 }}
              className="text-scramble select-none"
              style={{
                fontFamily: "var(--font-grotesk)",
                fontWeight: 700,
                fontSize: "clamp(4.5rem, 13vw, 16rem)",
                lineHeight: 0.82,
                letterSpacing: "-0.06em",
                color: "#F8F8F8",
                textWrap: "balance",
              }}
            >
              {heroText || "SENTINEL"}
            </motion.h1>

            {/* Sub-tagline in editorial italic — contrasting font */}
            <motion.p
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 1.4, ease: [0.16, 1, 0.3, 1], delay: 1.8 }}
              className="mt-8 sm:mt-12 text-editorial-italic text-white/60"
              style={{ maxWidth: "22ch" }}
            >
              Build what outlives you.
            </motion.p>
          </div>

          {/* Right: The Monolith — offset, with floating pills around it */}
          <div className="relative flex items-center justify-center lg:justify-end">
            <motion.div
              initial={{ opacity: 0, scale: 0.88, rotate: -5 }}
              animate={{ opacity: 0.85, scale: 1, rotate: 0 }}
              transition={{ duration: 2.8, ease: [0.16, 1, 0.3, 1], delay: 0.3 }}
              className="relative"
            >
              <Monolith size={280} />
            </motion.div>

            {/* Floating data pills around the monolith (mouse-reactive) */}
            {DATA_PILLS.map((pill, i) => {
              const offsetX = useTransform(springX, [0, 1], [-15 - i * 3, 15 + i * 3]);
              const offsetY = useTransform(springY, [0, 1], [-10 - i * 2, 10 + i * 2]);
              return (
                <motion.div
                  key={pill.label}
                  initial={{ opacity: 0, scale: 0.8 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{
                    duration: 1,
                    ease: [0.16, 1, 0.3, 1],
                    delay: 2.2 + i * 0.15,
                  }}
                  style={{
                    x: offsetX,
                    y: offsetY,
                    position: "absolute",
                    left: `${pill.x - 50 + 50}%`,
                    top: `${pill.y - 50 + 50}%`,
                  }}
                  className="hidden sm:flex data-pill"
                >
                  <span className="text-white/35">{pill.label}</span>
                  <span className="text-white/80 font-medium">{pill.value}</span>
                  <span
                    className={
                      pill.change.startsWith("+")
                        ? "text-[#00FF9D]"
                        : pill.change.startsWith("-")
                        ? "text-[#FF5B5B]"
                        : "text-[#00E5FF]"
                    }
                  >
                    {pill.change}
                  </span>
                </motion.div>
              );
            })}
          </div>
        </div>

        {/* Bottom bar: CTA + eyebrow — deliberately uneven spacing */}
        <motion.div
          initial={{ opacity: 0, y: 40 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 1.4, ease: [0.16, 1, 0.3, 1], delay: 2.4 }}
          className="mt-20 sm:mt-28 flex flex-col sm:flex-row items-start sm:items-center gap-6 sm:gap-10"
        >
          <Link
            href={signedIn ? "/dashboard" : "/signup"}
            className="enter-button"
            aria-label={signedIn ? "Open dashboard" : "Launch Sentinel"}
          >
            <span>{signedIn ? "OPEN DASHBOARD" : "LAUNCH AGENT"}</span>
            <span className="arrow" aria-hidden>
              →
            </span>
          </Link>

          {!signedIn && (
            <Link
              href="/login"
              className="font-mono text-[11px] tracking-[0.3em] uppercase text-white/30 hover:text-white transition-colors duration-700"
            >
              SIGN IN
            </Link>
          )}

          {/* Spacer pushes the eyebrow right */}
          <div className="hidden sm:block flex-1" />

          <div className="flex items-center gap-3">
            <span className="w-8 h-px bg-white/15" />
            <span className="font-mono text-[10px] tracking-[0.28em] uppercase text-white/30">
              Autonomous · Trading · Intelligence
            </span>
          </div>
        </motion.div>
      </div>

      {/* Bottom-left index */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1.4, ease: [0.16, 1, 0.3, 1], delay: 2.8 }}
        className="absolute bottom-6 left-5 sm:bottom-8 sm:left-8 z-20 hidden sm:flex items-center gap-3"
      >
        <span className="index-num">001 / 008</span>
        <span className="w-px h-3 bg-white/15" />
        <span className="godboy-mark" style={{ color: "rgba(255,255,255,0.25)" }}>
          PRESENCE
        </span>
      </motion.div>

      {/* Bottom-right scroll hint — longer, more dramatic */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1.4, ease: [0.16, 1, 0.3, 1], delay: 2.8 }}
        className="absolute bottom-6 right-5 sm:bottom-8 sm:right-8 z-20 hidden sm:flex flex-col items-end gap-2"
      >
        <span className="font-mono text-[9px] tracking-[0.4em] uppercase text-white/25">
          SCROLL
        </span>
        <motion.div
          animate={{ y: [0, 8, 0] }}
          transition={{ duration: 3.5, ease: "easeInOut", repeat: Infinity }}
          className="w-px h-12 bg-gradient-to-b from-white/30 to-transparent"
        />
      </motion.div>
    </section>
  );
}
