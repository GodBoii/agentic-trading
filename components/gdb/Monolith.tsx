"use client";

import { motion, MotionValue, useTransform } from "framer-motion";

/**
 * Monolith — a symbolic celestial artifact.
 * Part monolith. Part crown. Part celestial object.
 * Barely visible. Only revealed through light.
 *
 * It also breaks into 5 fragments (knowledge, capital, systems,
 * influence, legacy) as the user scrolls. `progress` (0→1) drives that
 * dispersal; passing progress=1 reassembles the object whole.
 */
export default function Monolith({
  progress,
  size = 520,
  showFragments = false,
  reduced = false,
}: {
  /** 0 = whole monolith, 1 = fully dispersed into 5 fragments */
  progress?: MotionValue<number>;
  size?: number;
  showFragments?: boolean;
  reduced?: boolean;
}) {
  const half = size / 2;
  const coreR = size * 0.16;
  const ring1R = size * 0.28;
  const ring2R = size * 0.38;
  const ring3R = size * 0.46;

  // Default no-op motion value if progress is undefined
  const p = progress ?? ({ get: () => 0 } as unknown as MotionValue<number>);

  // Fragment vectors — five directions on a clock face
  const fragments = [
    { label: "KNOWLEDGE",  angle: -90, distance: size * 0.85 },
    { label: "CAPITAL",    angle: -18, distance: size * 0.85 },
    { label: "SYSTEMS",    angle:  54, distance: size * 0.85 },
    { label: "INFLUENCE",  angle: 126, distance: size * 0.85 },
    { label: "LEGACY",     angle: 198, distance: size * 0.85 },
  ];

  return (
    <div
      className="monolith-stage"
      style={{ width: size, height: size }}
      aria-hidden
    >
      {/* Layer 1 — outermost faint ring with gold glint (slowest) */}
      <div
        className={reduced ? "" : "monolith monolith-rotate-1"}
        style={{ position: "absolute", inset: 0 }}
      >
        <svg viewBox={`0 0 ${size} ${size}`} width="100%" height="100%">
          <defs>
            <linearGradient id="ring-outer" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="rgba(255,255,255,0.18)" />
              <stop offset="35%" stopColor="rgba(255,255,255,0.02)" />
              <stop offset="60%" stopColor="rgba(212,175,55,0.18)" />
              <stop offset="100%" stopColor="rgba(255,255,255,0.10)" />
            </linearGradient>
            <linearGradient id="spoke-grad" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="rgba(255,255,255,0.0)" />
              <stop offset="50%" stopColor="rgba(255,255,255,0.35)" />
              <stop offset="100%" stopColor="rgba(255,255,255,0.0)" />
            </linearGradient>
          </defs>

          <circle
            cx={half} cy={half} r={ring3R}
            fill="none" stroke="url(#ring-outer)" strokeWidth="0.6"
          />
          {Array.from({ length: 60 }).map((_, i) => {
            const a = (i / 60) * Math.PI * 2;
            const r1 = ring3R - 0.5;
            const r2 = ring3R - (i % 5 === 0 ? 6 : 3);
            const x1 = half + Math.cos(a) * r1;
            const y1 = half + Math.sin(a) * r1;
            const x2 = half + Math.cos(a) * r2;
            const y2 = half + Math.sin(a) * r2;
            return (
              <line
                key={`tick-${i}`}
                x1={x1} y1={y1} x2={x2} y2={y2}
                stroke={i % 5 === 0 ? "rgba(255,255,255,0.55)" : "rgba(255,255,255,0.18)"}
                strokeWidth={i % 5 === 0 ? 0.8 : 0.4}
              />
            );
          })}
        </svg>
      </div>

      {/* Layer 2 — middle ring (counter-rotating) */}
      <div
        className={reduced ? "" : "monolith monolith-rotate-2"}
        style={{ position: "absolute", inset: 0 }}
      >
        <svg viewBox={`0 0 ${size} ${size}`} width="100%" height="100%">
          <circle
            cx={half} cy={half} r={ring2R}
            fill="none" stroke="rgba(255,255,255,0.10)" strokeWidth="0.5"
            strokeDasharray="1 6"
          />
          <circle
            cx={half} cy={half} r={ring1R}
            fill="none" stroke="rgba(255,255,255,0.22)" strokeWidth="0.6"
          />
          {[0, 90, 180, 270].map((deg) => {
            const a = (deg * Math.PI) / 180;
            const r1 = ring1R + 4;
            const r2 = ring2R - 4;
            return (
              <line
                key={`spoke-${deg}`}
                x1={half + Math.cos(a) * r1}
                y1={half + Math.sin(a) * r1}
                x2={half + Math.cos(a) * r2}
                y2={half + Math.sin(a) * r2}
                stroke="url(#spoke-grad)"
                strokeWidth="0.8"
              />
            );
          })}
        </svg>
      </div>

      {/* Layer 3 — the core (with breathing) */}
      <motion.div
        className="monolith"
        style={{ position: "absolute", inset: 0 }}
        animate={reduced ? undefined : { opacity: [0.9, 1, 0.9], scale: [1, 1.012, 1] }}
        transition={reduced ? undefined : { duration: 8, ease: "easeInOut", repeat: Infinity }}
      >
        <svg viewBox={`0 0 ${size} ${size}`} width="100%" height="100%">
          <defs>
            <radialGradient id="core-grad" cx="0.4" cy="0.35" r="0.7">
              <stop offset="0%" stopColor="rgba(255,255,255,0.95)" />
              <stop offset="22%" stopColor="rgba(255,255,255,0.55)" />
              <stop offset="55%" stopColor="rgba(255,255,255,0.18)" />
              <stop offset="100%" stopColor="rgba(255,255,255,0.02)" />
            </radialGradient>
            <radialGradient id="core-gold" cx="0.7" cy="0.75" r="0.5">
              <stop offset="0%" stopColor="rgba(212,175,55,0.45)" />
              <stop offset="100%" stopColor="rgba(212,175,55,0)" />
            </radialGradient>
          </defs>
          <circle cx={half} cy={half} r={coreR * 2.1} fill="url(#core-grad)" opacity="0.5" />
          <circle cx={half} cy={half} r={coreR} fill="rgba(255,255,255,0.92)" />
          <circle
            cx={half + coreR * 0.35} cy={half + coreR * 0.45}
            r={coreR * 0.9}
            fill="url(#core-gold)"
            style={{ mixBlendMode: "screen" }}
          />
          {Array.from({ length: 5 }).map((_, i) => (
            <circle
              key={`ridge-${i}`}
              cx={half} cy={half}
              r={coreR * (0.25 + i * 0.15)}
              fill="none"
              stroke="rgba(0,0,0,0.08)"
              strokeWidth="0.5"
            />
          ))}
          <line x1={half - coreR * 0.7} y1={half} x2={half + coreR * 0.7} y2={half} stroke="rgba(0,0,0,0.25)" strokeWidth="0.4" />
          <line x1={half} y1={half - coreR * 0.7} x2={half} y2={half + coreR * 0.7} stroke="rgba(0,0,0,0.25)" strokeWidth="0.4" />
        </svg>
      </motion.div>

      {/* Optional — the 5 fragments fly out as progress → 1 */}
      {showFragments && (
        <div className="absolute inset-0 pointer-events-none">
          {fragments.map((f) => (
            <Fragment key={f.label} p={p} angle={f.angle} distance={f.distance} label={f.label} />
          ))}
        </div>
      )}
    </div>
  );
}

function Fragment({
  p,
  angle,
  distance,
  label,
}: {
  p: MotionValue<number>;
  angle: number;
  distance: number;
  label: string;
}) {
  const a = (angle * Math.PI) / 180;
  const x = useTransform(p, [0, 1], [0, Math.cos(a) * distance]);
  const y = useTransform(p, [0, 1], [0, Math.sin(a) * distance]);
  const opacity = useTransform(p, [0, 0.3, 1], [0, 1, 0.85]);
  const scale = useTransform(p, [0, 1], [0.5, 1]);
  return (
    <motion.div
      style={{ x, y, opacity, scale }}
      className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2"
    >
      <div className="flex flex-col items-center gap-3">
        <div
          className="rounded-full"
          style={{
            width: 8,
            height: 8,
            background: "rgba(255,255,255,0.95)",
            boxShadow: "0 0 18px rgba(255,255,255,0.55), 0 0 36px rgba(212,175,55,0.18)",
          }}
        />
        <span className="text-tag-godboy text-white/55">{label}</span>
      </div>
    </motion.div>
  );
}
