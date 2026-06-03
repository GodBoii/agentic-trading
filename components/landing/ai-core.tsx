"use client";

import { motion } from "framer-motion";

/**
 * 3D Autonomous Trading Intelligence Core
 * Pure SVG with layered depth — no WebGL, instant render, SSR-safe.
 * Five orbiting agent nodes + pulsing inner core + energy beams.
 */
export default function AICore() {
  const agents = [
    { id: "market", label: "Market", angle: 0, color: "#00D4FF", radius: 175, size: 44 },
    { id: "risk", label: "Risk", angle: 72, color: "#00FF88", radius: 175, size: 38 },
    { id: "execution", label: "Execution", angle: 144, color: "#A78BFA", radius: 175, size: 46 },
    { id: "research", label: "Research", angle: 216, color: "#F472B6", radius: 175, size: 40 },
    { id: "portfolio", label: "Portfolio", angle: 288, color: "#FFB800", radius: 175, size: 42 },
  ];

  const innerOrbiters = [
    { angle: 0, size: 3, dist: 55, color: "#00D4FF", delay: 0 },
    { angle: 60, size: 2.5, dist: 60, color: "#00FF88", delay: 0.5 },
    { angle: 120, size: 3, dist: 55, color: "#A78BFA", delay: 1 },
    { angle: 180, size: 2.5, dist: 60, color: "#F472B6", delay: 1.5 },
    { angle: 240, size: 3, dist: 55, color: "#FFB800", delay: 2 },
    { angle: 300, size: 2.5, dist: 60, color: "#00D4FF", delay: 2.5 },
  ];

  return (
    <div className="relative w-full aspect-square max-w-[640px] mx-auto select-none pointer-events-none">
      {/* Ambient glow layers — depth via stacked blurs */}
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="absolute h-[60%] w-[60%] rounded-full bg-accent/[0.06] blur-[100px] animate-drift-slow" />
        <div className="absolute h-[40%] w-[40%] rounded-full bg-success/[0.05] blur-[80px] animate-drift" />
      </div>

      {/* Outer ring system — orbital paths */}
      <svg
        viewBox="0 0 600 600"
        className="absolute inset-0 w-full h-full"
        style={{ overflow: "visible" }}
      >
        <defs>
          {/* Radial gradient for core sphere */}
          <radialGradient id="coreGrad" cx="50%" cy="40%" r="50%">
            <stop offset="0%" stopColor="#ffffff" stopOpacity="0.9" />
            <stop offset="30%" stopColor="#00D4FF" stopOpacity="0.8" />
            <stop offset="70%" stopColor="#0066AA" stopOpacity="0.6" />
            <stop offset="100%" stopColor="#001A2E" stopOpacity="0.9" />
          </radialGradient>

          <radialGradient id="coreGradInner" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#ffffff" stopOpacity="1" />
            <stop offset="40%" stopColor="#00D4FF" stopOpacity="0.6" />
            <stop offset="100%" stopColor="#00D4FF" stopOpacity="0" />
          </radialGradient>

          {/* Energy beam gradient */}
          <linearGradient id="beamGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#00D4FF" stopOpacity="0" />
            <stop offset="50%" stopColor="#00D4FF" stopOpacity="0.8" />
            <stop offset="100%" stopColor="#00FF88" stopOpacity="0" />
          </linearGradient>

          <linearGradient id="beamGradRev" x1="100%" y1="0%" x2="0%" y2="0%">
            <stop offset="0%" stopColor="#00D4FF" stopOpacity="0" />
            <stop offset="50%" stopColor="#A78BFA" stopOpacity="0.6" />
            <stop offset="100%" stopColor="#00D4FF" stopOpacity="0" />
          </linearGradient>

          {/* Glow filter */}
          <filter id="glow-sm" x="-100%" y="-100%" width="300%" height="300%">
            <feGaussianBlur stdDeviation="2" />
          </filter>
          <filter id="glow-md" x="-100%" y="-100%" width="300%" height="300%">
            <feGaussianBlur stdDeviation="4" />
          </filter>
          <filter id="glow-lg" x="-100%" y="-100%" width="300%" height="300%">
            <feGaussianBlur stdDeviation="8" />
          </filter>
        </defs>

        {/* === ORBITAL PATHS === */}
        {/* Outer orbit — agents */}
        <g transform="translate(300, 300)">
          <circle
            r="175"
            fill="none"
            stroke="rgba(255,255,255,0.06)"
            strokeWidth="1"
            strokeDasharray="2 6"
          />
          <circle
            r="175"
            fill="none"
            stroke="url(#beamGrad)"
            strokeWidth="1.5"
            opacity="0.3"
            transform="rotate(20)"
          />
        </g>

        {/* Mid orbit */}
        <g transform="translate(300, 300)">
          <circle
            r="115"
            fill="none"
            stroke="rgba(255,255,255,0.05)"
            strokeWidth="1"
            strokeDasharray="1 4"
          />
        </g>

        {/* Inner orbit — orbital electrons */}
        <g transform="translate(300, 300)">
          <circle
            r="60"
            fill="none"
            stroke="rgba(0, 212, 255, 0.15)"
            strokeWidth="1"
          />
        </g>

        {/* === ENERGY BEAMS (connecting agents through core) === */}
        <g transform="translate(300, 300)" opacity="0.5">
          {[0, 72, 144, 216, 288].map((angle, i) => {
            const rad = (angle * Math.PI) / 180;
            const x = Math.cos(rad) * 175;
            const y = Math.sin(rad) * 175;
            return (
              <line
                key={`beam-${i}`}
                x1={-x * 0.3}
                y1={-y * 0.3}
                x2={x}
                y2={y}
                stroke="url(#beamGrad)"
                strokeWidth="0.5"
                strokeDasharray="2 8"
                opacity="0.4"
              >
                <animate
                  attributeName="stroke-dashoffset"
                  from="0"
                  to="-20"
                  dur="2s"
                  repeatCount="indefinite"
                />
              </line>
            );
          })}
        </g>

        {/* === INNER CORE === */}
        <g transform="translate(300, 300)">
          {/* Outer halo */}
          <circle r="80" fill="url(#coreGradInner)" opacity="0.3">
            <animate
              attributeName="r"
              values="75;90;75"
              dur="4s"
              repeatCount="indefinite"
            />
            <animate
              attributeName="opacity"
              values="0.2;0.4;0.2"
              dur="4s"
              repeatCount="indefinite"
            />
          </circle>

          {/* Core sphere */}
          <circle r="55" fill="url(#coreGrad)" filter="url(#glow-md)">
            <animate
              attributeName="r"
              values="54;57;54"
              dur="3s"
              repeatCount="indefinite"
            />
          </circle>

          {/* Inner bright spot */}
          <circle r="20" fill="#ffffff" opacity="0.8" filter="url(#glow-sm)">
            <animate
              attributeName="opacity"
              values="0.6;1;0.6"
              dur="2s"
              repeatCount="indefinite"
            />
          </circle>

          {/* Core ring */}
          <circle
            r="55"
            fill="none"
            stroke="rgba(255,255,255,0.4)"
            strokeWidth="1"
            transform="rotate(45)"
          />
        </g>

        {/* === ORBITAL ELECTRONS (rotating) === */}
        <g transform="translate(300, 300)">
          <animateTransform
            attributeName="transform"
            type="rotate"
            from="0"
            to="360"
            dur="20s"
            repeatCount="indefinite"
            additive="sum"
          />
          {innerOrbiters.map((orb, i) => {
            const rad = (orb.angle * Math.PI) / 180;
            return (
              <circle
                key={`orb-${i}`}
                cx={Math.cos(rad) * orb.dist}
                cy={Math.sin(rad) * orb.dist}
                r={orb.size}
                fill={orb.color}
                opacity="0.9"
                filter="url(#glow-sm)"
              >
                <animate
                  attributeName="opacity"
                  values="0.4;1;0.4"
                  dur={`${1.5 + i * 0.3}s`}
                  repeatCount="indefinite"
                  begin={`${orb.delay}s`}
                />
              </circle>
            );
          })}
        </g>

        {/* Reverse-rotating outer ring */}
        <g transform="translate(300, 300)">
          <animateTransform
            attributeName="transform"
            type="rotate"
            from="360"
            to="0"
            dur="40s"
            repeatCount="indefinite"
            additive="sum"
          />
          <circle
            r="200"
            fill="none"
            stroke="rgba(255,255,255,0.03)"
            strokeWidth="1"
            strokeDasharray="20 40"
          />
        </g>
      </svg>

      {/* === AGENT NODES (overlaid) === */}
      {/* Container rotates slowly */}
      <motion.div
        className="absolute inset-0"
        animate={{ rotate: 360 }}
        transition={{ duration: 60, repeat: Infinity, ease: "linear" }}
      >
        {agents.map((agent) => {
          const rad = (agent.angle * Math.PI) / 180;
          const xPct = 50 + (Math.cos(rad) * 175) / 6; // 600px viewbox -> %
          const yPct = 50 + (Math.sin(rad) * 175) / 6;

          return (
            <div
              key={agent.id}
              className="absolute"
              style={{
                left: `${xPct}%`,
                top: `${yPct}%`,
                transform: "translate(-50%, -50%)",
              }}
            >
              {/* Counter-rotate so node stays upright */}
              <motion.div
                animate={{ rotate: -360 }}
                transition={{ duration: 60, repeat: Infinity, ease: "linear" }}
                className="relative"
                style={{ width: agent.size, height: agent.size }}
              >
                <div
                  className="absolute inset-0 rounded-full"
                  style={{
                    background: `radial-gradient(circle, ${agent.color}40 0%, ${agent.color}00 70%)`,
                    filter: "blur(8px)",
                  }}
                />
                <div
                  className="relative h-full w-full rounded-full border border-white/20 backdrop-blur-md flex items-center justify-center"
                  style={{
                    background: `linear-gradient(135deg, ${agent.color}30 0%, rgba(14,14,16,0.9) 100%)`,
                    boxShadow: `0 0 20px ${agent.color}40, inset 0 1px 0 rgba(255,255,255,0.1)`,
                  }}
                >
                  <div
                    className="h-1.5 w-1.5 rounded-full"
                    style={{ background: agent.color }}
                  />
                </div>
              </motion.div>
            </div>
          );
        })}
      </motion.div>

      {/* Static agent labels (not rotating) */}
      <div className="absolute inset-0 pointer-events-none">
        {agents.map((agent) => {
          const rad = (agent.angle * Math.PI) / 180;
          const xPct = 50 + (Math.cos(rad) * 175) / 6;
          const yPct = 50 + (Math.sin(rad) * 175) / 6;

          return (
            <div
              key={`label-${agent.id}`}
              className="absolute"
              style={{
                left: `${xPct}%`,
                top: `${yPct}%`,
                transform: `translate(-50%, ${agent.angle > 0 && agent.angle < 180 ? "calc(-100% - 22px)" : "calc(0% + 22px)"})`,
              }}
            >
              <div className="flex flex-col items-center gap-0.5">
                <div
                  className="text-[9px] font-mono uppercase tracking-[0.2em] px-1.5 py-0.5 rounded-sm"
                  style={{
                    color: agent.color,
                    background: `${agent.color}10`,
                    border: `1px solid ${agent.color}30`,
                  }}
                >
                  {agent.label}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
