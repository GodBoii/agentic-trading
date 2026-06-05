"use client";

import { motion } from "framer-motion";
import { useEffect, useMemo, useState } from "react";

/**
 * IntelligenceCore — the living, breathing object at the center of the hero.
 *
 * Composition (back → front):
 *  1. signal-mesh   — fine grid that fades toward the edges
 *  2. radial halo   — a large soft glow behind the sphere
 *  3. flow lines    — curved SVG paths that the 6 streams travel along
 *  4. core sphere   — the actual glowing intelligence orb (3 stacked divs)
 *  5. core rings    — 3 orbiting wireframe rings at different speeds
 *  6. core streams  — 6 glass pills (Equities / Options / Forex / Crypto / Macro / News)
 *
 * The sphere itself uses layered radial-gradients + inset shadows — no canvas,
 * no WebGL, so it renders identically on iOS Safari and a 4K monitor.
 */

const STREAMS = [
  { label: "Equities",    color: "#00E5FF" },
  { label: "Options",     color: "#00E5FF" },
  { label: "Forex",       color: "#00FF9D" },
  { label: "Crypto",      color: "#00FF9D" },
  { label: "Macro",       color: "#F8F8F8" },
  { label: "News",        color: "#F8F8F8" },
] as const;

// Curved path for a single flow line. Start at the matching stream pill and
// arc into the sphere center.
function buildPath(from: { x: number; y: number }) {
  const cx = 50, cy = 50;
  const mx = (from.x + cx) / 2;
  const my = (from.y + cy) / 2 - 8; // gentle upward bow
  return `M ${from.x} ${from.y} Q ${mx} ${my} ${cx} ${cy}`;
}

const FLOW_ORIGINS = [
  { x: 50, y: 8  },  // top stream → Equities
  { x: 96, y: 50 },  // right → Options
  { x: 50, y: 92 },  // bottom → Forex
  { x: 4,  y: 50 },  // left → Crypto
  { x: 82, y: 22 },  // top-right → Macro
  { x: 18, y: 78 },  // bottom-left → News
];

export default function IntelligenceCore() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const paths = useMemo(() => FLOW_ORIGINS.map(buildPath), []);

  return (
    <div className="absolute inset-0 overflow-hidden">
      <div className="signal-mesh" />

      {/* SVG flow network — drawn behind the sphere */}
      <svg
        className="absolute inset-0 h-full w-full"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        <defs>
          <radialGradient id="halo" cx="50%" cy="50%" r="50%">
            <stop offset="0%"  stopColor="#00E5FF" stopOpacity="0.30" />
            <stop offset="55%" stopColor="#00E5FF" stopOpacity="0.05" />
            <stop offset="100%" stopColor="#00E5FF" stopOpacity="0" />
          </radialGradient>
          <filter id="soft-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="0.6" />
          </filter>
        </defs>

        {/* Wide soft halo */}
        <circle cx="50" cy="50" r="48" fill="url(#halo)" />

        {/* Flowing signal lines */}
        <g filter="url(#soft-glow)">
          {paths.map((d, i) => (
            <g key={i}>
              <path
                d={d}
                stroke="rgba(0,229,255,0.10)"
                strokeWidth="0.18"
                fill="none"
              />
              <path
                d={d}
                className="flow-line"
                strokeWidth="0.22"
                style={{ animationDelay: `${i * -0.5}s` }}
              />
            </g>
          ))}
        </g>
      </svg>

      {/* The sphere + rings */}
      <div className="core-shell">
        <div className="absolute" style={{ width: "clamp(320px, 42vw, 580px)", aspectRatio: "1" }}>
          <div className="core-rings">
            <span className="core-ring core-ring-1" />
            <span className="core-ring core-ring-2" />
            <span className="core-ring core-ring-3" />
          </div>
          <div className="core-sphere" />
        </div>

        {STREAMS.map((s) => (
          <div key={s.label} className="core-stream">
            <span>{s.label}</span>
          </div>
        ))}
      </div>

      {/* Subtle entrance */}
      {mounted && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 1.6, ease: [0.16, 1, 0.3, 1] }}
          className="absolute inset-0 pointer-events-none"
        />
      )}
    </div>
  );
}
