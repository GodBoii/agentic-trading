"use client";

import { useEffect, useState } from "react";
import Hero from "./Hero";
import Command from "./Command";
import FinalEra from "./FinalEra";

/**
 * GODBOY — an iconic landing page.
 * Six acts: Presence (hero) + 5 commands + Era (final).
 * Pure black void. Massive editorial typography. Gold used like a luxury watch.
 */
export default function GodboyLanding() {
  const [scrollProgress, setScrollProgress] = useState(0);

  useEffect(() => {
    const onScroll = () => {
      const h = document.documentElement;
      const max = h.scrollHeight - h.clientHeight;
      const p = max > 0 ? h.scrollTop / max : 0;
      setScrollProgress(p);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <main className="relative bg-black text-white">
      {/* Top scroll progress hairline (gold) */}
      <div
        className="scroll-hairline"
        style={{ ["--scroll-progress" as string]: scrollProgress.toFixed(4) }}
      />

      <Hero />

      <Command
        index="002"
        total="005"
        tag="COMMAND I"
        word="KNOWLEDGE"
        caption="Every empire begins as an idea."
        accentDot
      />

      <Command
        index="003"
        total="005"
        tag="COMMAND II"
        word="CAPITAL"
        caption="Money is stored energy."
        accentDot
      />

      <Command
        index="004"
        total="005"
        tag="COMMAND III"
        word="SYSTEMS"
        caption="Freedom is engineered."
        accentDot
      />

      <Command
        index="005"
        total="005"
        tag="COMMAND IV"
        word="INFLUENCE"
        caption="Attention moves nations."
        accentDot
      />

      <Command
        index="006"
        total="005"
        tag="COMMAND V"
        word="LEGACY"
        caption="Build beyond yourself."
        accentDot
      />

      <FinalEra />
    </main>
  );
}
