"use client";

import { motion } from "framer-motion";

const ease = [0.16, 1, 0.3, 1] as const;

const PILLARS = [
  {
    label: "SOC 2",
    sub: "Type II Ready",
    desc: "Independently audited controls across security, availability, and confidentiality.",
  },
  {
    label: "AES-256",
    sub: "Encryption at rest",
    desc: "All credentials and tokens encrypted with hardware-backed key management.",
  },
  {
    label: "Broker API",
    sub: "OAuth-secured",
    desc: "Direct integration with regulated broker APIs. No withdrawal rights, ever.",
  },
  {
    label: "Real-Time",
    sub: "Monitoring",
    desc: "Sub-second telemetry across every order, fill, and risk gate.",
  },
  {
    label: "Institutional",
    sub: "Infrastructure",
    desc: "Multi-region redundancy. 99.99% uptime. Hot failover across availability zones.",
  },
];

export default function Trust() {
  return (
    <section className="relative bg-[#050505] py-32 overflow-hidden">
      {/* Subtle grid */}
      <div className="absolute inset-0 bg-grid opacity-50 pointer-events-none" />

      <div className="relative mx-auto max-w-7xl px-6 lg:px-8">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.8, ease }}
          className="flex flex-col gap-6 max-w-3xl mb-20"
        >
          <div className="inline-flex items-center gap-2">
            <span className="h-px w-8 bg-accent" />
            <span className="text-[11px] font-mono uppercase tracking-[0.22em] text-accent">
              Trust & Infrastructure
            </span>
          </div>
          <h2 className="font-display text-display-lg text-white text-balance">
            Built like a{" "}
            <span className="font-serif-italic text-ink-secondary">bank.</span>
            <br />
            Audited like one.
          </h2>
          <p className="text-[16px] text-ink-secondary max-w-xl leading-relaxed">
            Every layer engineered to institutional standards — from the
            cryptographic primitives to the disaster-recovery topology.
          </p>
        </motion.div>

        {/* Architecture diagram */}
        <motion.div
          initial={{ opacity: 0, y: 32 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.9, ease }}
          className="surface rounded-3xl p-8 lg:p-12 mb-12 relative overflow-hidden"
        >
          <div className="flex items-center justify-between mb-10">
            <div>
              <div className="text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary mb-2">
                System topology
              </div>
              <h3 className="font-display text-[24px] text-white tracking-[-0.02em]">
                Multi-region autonomous infrastructure
              </h3>
            </div>
            <div className="hidden sm:flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-success animate-pulse-soft" />
              <span className="text-[11px] font-mono uppercase tracking-[0.18em] text-success">
                All systems nominal
              </span>
            </div>
          </div>

          <ArchitectureDiagram />

          {/* Latency bar */}
          <div className="mt-10 pt-8 border-t border-line grid grid-cols-1 sm:grid-cols-3 gap-6">
            {[
              { region: "Mumbai · ap-south-1", lat: "12ms" },
              { region: "Singapore · ap-southeast-1", lat: "28ms" },
              { region: "Frankfurt · eu-central-1", lat: "84ms" },
            ].map((r) => (
              <div key={r.region} className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="h-1.5 w-1.5 rounded-full bg-accent" />
                  <span className="text-[12px] font-mono text-ink-secondary">
                    {r.region}
                  </span>
                </div>
                <span className="text-[12px] font-mono text-white nums">
                  {r.lat}
                </span>
              </div>
            ))}
          </div>
        </motion.div>

        {/* Compliance pillars */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-px bg-line rounded-2xl overflow-hidden border border-line">
          {PILLARS.map((p, i) => (
            <motion.div
              key={p.label}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-50px" }}
              transition={{ duration: 0.5, ease, delay: i * 0.05 }}
              className="bg-[#08080a] p-7 surface-hover"
            >
              <div className="text-[20px] font-display text-white tracking-[-0.02em] mb-1">
                {p.label}
              </div>
              <div className="text-[11px] font-mono uppercase tracking-[0.18em] text-accent mb-5">
                {p.sub}
              </div>
              <p className="text-[13px] text-ink-secondary leading-relaxed">
                {p.desc}
              </p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}

function ArchitectureDiagram() {
  return (
    <div className="relative h-[300px] sm:h-[340px]">
      <svg
        viewBox="0 0 1000 340"
        className="w-full h-full"
        preserveAspectRatio="xMidYMid meet"
      >
        <defs>
          <linearGradient id="trust-line" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#00D4FF" stopOpacity="0" />
            <stop offset="50%" stopColor="#00D4FF" stopOpacity="0.5" />
            <stop offset="100%" stopColor="#00D4FF" stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* Connection lines */}
        {[0, 1, 2, 3].map((i) => {
          const y = 80 + i * 50;
          return (
            <g key={i}>
              <line
                x1="120"
                y1={y}
                x2="380"
                y2={170}
                stroke="rgba(255,255,255,0.06)"
                strokeWidth="1"
              />
              <line
                x1="620"
                y1={170}
                x2="880"
                y2={y}
                stroke="rgba(255,255,255,0.06)"
                strokeWidth="1"
              />
            </g>
          );
        })}

        {/* Animated data flow lines */}
        <line
          x1="120"
          y1="170"
          x2="380"
          y2="170"
          stroke="url(#trust-line)"
          strokeWidth="1.5"
        >
          <animate
            attributeName="stroke-dasharray"
            values="0 1000;1000 0"
            dur="3s"
            repeatCount="indefinite"
          />
        </line>

        <line
          x1="620"
          y1="170"
          x2="880"
          y2="170"
          stroke="url(#trust-line)"
          strokeWidth="1.5"
        >
          <animate
            attributeName="stroke-dasharray"
            values="0 1000;1000 0"
            dur="3s"
            repeatCount="indefinite"
            begin="1.5s"
          />
        </line>

        {/* LEFT — Client layer */}
        <g transform="translate(40, 30)">
          <text
            x="0"
            y="0"
            fill="#52525B"
            fontSize="10"
            fontFamily="monospace"
            letterSpacing="2"
          >
            CLIENT
          </text>
          {["Dashboard", "Mobile", "API"].map((label, i) => {
            const y = 30 + i * 50;
            return (
              <g key={label} transform={`translate(0, ${y})`}>
                <rect
                  x="0"
                  y="0"
                  width="120"
                  height="36"
                  rx="6"
                  fill="rgba(14,14,16,1)"
                  stroke="rgba(255,255,255,0.1)"
                />
                <circle cx="14" cy="18" r="3" fill="#00D4FF" />
                <text
                  x="26"
                  y="22"
                  fill="#fff"
                  fontSize="12"
                  fontFamily="sans-serif"
                >
                  {label}
                </text>
              </g>
            );
          })}
        </g>

        {/* CENTER — Aetheria core */}
        <g transform="translate(420, 90)">
          <rect
            x="0"
            y="0"
            width="160"
            height="160"
            rx="12"
            fill="rgba(0,212,255,0.03)"
            stroke="rgba(0,212,255,0.3)"
            strokeWidth="1.5"
          />
          <text
            x="80"
            y="-12"
            fill="#00D4FF"
            fontSize="10"
            fontFamily="monospace"
            letterSpacing="2"
            textAnchor="middle"
          >
            AETHERIA CORE
          </text>

          {/* Inner hex */}
          <g transform="translate(80, 80)">
            <polygon
              points="0,-30 26,-15 26,15 0,30 -26,15 -26,-15"
              fill="rgba(0,212,255,0.05)"
              stroke="#00D4FF"
              strokeWidth="1.5"
            />
            <circle r="20" fill="rgba(0,212,255,0.1)" />
            <circle r="8" fill="#00D4FF">
              <animate
                attributeName="r"
                values="6;10;6"
                dur="2s"
                repeatCount="indefinite"
              />
            </circle>
          </g>

          {/* Stacked labels */}
          <text
            x="80"
            y="150"
            fill="#A1A1AA"
            fontSize="10"
            fontFamily="monospace"
            letterSpacing="1.5"
            textAnchor="middle"
          >
            ENCRYPTED · AUDITED
          </text>
        </g>

        {/* RIGHT — Broker layer */}
        <g transform="translate(820, 30)">
          <text
            x="0"
            y="0"
            fill="#52525B"
            fontSize="10"
            fontFamily="monospace"
            letterSpacing="2"
          >
            BROKER
          </text>
          {["Dhan", "Zerodha", "IBKR"].map((label, i) => {
            const y = 30 + i * 50;
            return (
              <g key={label} transform={`translate(0, ${y})`}>
                <rect
                  x="0"
                  y="0"
                  width="120"
                  height="36"
                  rx="6"
                  fill="rgba(14,14,16,1)"
                  stroke="rgba(255,255,255,0.1)"
                />
                <circle cx="14" cy="18" r="3" fill="#00FF88" />
                <text
                  x="26"
                  y="22"
                  fill="#fff"
                  fontSize="12"
                  fontFamily="sans-serif"
                >
                  {label}
                </text>
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}
