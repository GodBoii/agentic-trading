"use client";

import { motion } from "framer-motion";
import { type CSSProperties, useEffect, useState } from "react";

const spring = { type: "spring", stiffness: 120, damping: 20, bounce: 0 } as const;

const agents = [
  { name: "Research Agent", scans: ["News", "Filings", "Economic Data", "Social Signals"], x: "18%", y: "22%" },
  { name: "Signal Agent", scans: ["Opportunity Generation", "Regime Shift", "Flow Imbalance"], x: "68%", y: "28%" },
  { name: "Risk Agent", scans: ["Exposure", "Volatility", "Correlation"], x: "28%", y: "68%" },
  { name: "Execution Agent", scans: ["Routing", "Slippage", "Venue Quality"], x: "76%", y: "72%" },
];

const strategies = [
  ["01", "Momentum Intelligence", "2.71", "68.4%", "Signal velocity rising across liquid mid-cap universe."],
  ["02", "Market Structure", "2.18", "64.9%", "Liquidity pockets identified below current pressure band."],
  ["03", "Cross Asset Flow", "2.94", "71.2%", "FX impulse confirms equity risk-on continuation."],
  ["04", "Options Intelligence", "1.96", "62.8%", "Skew compression suggests controlled upside convexity."],
  ["05", "Macro Engine", "3.11", "73.6%", "Rates repricing absorbed; allocation bias remains constructive."],
];

const feed = [
  ["09:34:12", "Volatility spike detected.", "91.4%", "Reduce exposure by 12%", "Completed"],
  ["09:34:18", "News sentiment diverges from price action.", "88.7%", "Hold execution window", "Monitoring"],
  ["09:34:26", "Liquidity river thinning near resistance.", "93.2%", "Route passive orders", "Completed"],
  ["09:34:31", "Correlation cluster expanding.", "89.9%", "Rebalance hedge sleeve", "Completed"],
  ["09:34:44", "Macro impulse confirms risk budget.", "94.1%", "Increase allocation by 4%", "Queued"],
  ["09:34:52", "Execution trail shows low slippage.", "97.8%", "Continue agent routing", "Completed"],
];

function StatusCard() {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((value) => value + 1), 2600);
    return () => clearInterval(id);
  }, []);

  const rows = [
    ["Market State", "ACTIVE"],
    ["Signals Processed", (18437229 + tick * 58231).toLocaleString("en-US")],
    ["Agent Decisions", (4281 + tick * 17).toLocaleString("en-US")],
    ["Execution Accuracy", `${(97.8 + (tick % 4) * 0.03).toFixed(1)}%`],
  ];

  return (
    <motion.div
      initial={{ opacity: 0, x: 30 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ ...spring, delay: 0.35 }}
      className="glass-liquid absolute right-6 top-1/2 z-20 hidden w-[330px] -translate-y-1/2 p-5 lg:block"
    >
      <div className="mb-5 flex items-center justify-between">
        <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/45">Live system status</span>
        <span className="h-2 w-2 rounded-full bg-[#00FF9D] shadow-[0_0_18px_#00FF9D]" />
      </div>
      <div className="space-y-4">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-end justify-between border-b border-white/[0.06] pb-3">
            <span className="text-sm text-white/55">{label}</span>
            <motion.span
              key={value}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="nums font-mono text-sm text-[#F8F8F8]"
            >
              {value}
            </motion.span>
          </div>
        ))}
      </div>
    </motion.div>
  );
}

function IntelligenceCore() {
  const streams = ["Equities", "Options", "Forex", "Crypto", "Macro", "News"];
  return (
    <div className="absolute inset-0 overflow-hidden">
      <div className="signal-mesh" />
      <div className="core-shell">
        <div className="core-sphere" />
        {streams.map((stream, index) => (
          <div key={stream} className="core-stream" style={{ "--i": index } as CSSProperties}>
            <span>{stream}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Hero() {
  return (
    <section className="relative min-h-screen overflow-hidden bg-[#030303]">
      <IntelligenceCore />
      <div className="relative z-10 flex min-h-screen max-w-[1800px] flex-col justify-center px-5 py-28 sm:px-8 lg:px-14">
        <motion.p initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={spring} className="mb-8 font-mono text-[10px] uppercase tracking-[0.24em] text-white/45">
          Sentinel / Autonomous Capital OS
        </motion.p>
        <motion.h1 initial={{ opacity: 0, y: 34 }} animate={{ opacity: 1, y: 0 }} transition={{ ...spring, delay: 0.12 }} className="sentinel-hero-title">
          AUTONOMOUS<br />INTELLIGENCE<br />FOR GLOBAL<br />MARKETS
        </motion.h1>
        <motion.p initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ ...spring, delay: 0.25 }} className="mt-8 max-w-[520px] text-base leading-7 text-white/70 sm:text-lg">
          The first autonomous operating system for market research, execution, and portfolio intelligence.
        </motion.p>
        <motion.div initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ ...spring, delay: 0.36 }} className="mt-9 flex flex-col gap-3 sm:flex-row">
          <a href="/signup" className="liquid-button">Launch Agent</a>
          <a href="#agents" className="liquid-button liquid-button-muted">View Intelligence Layer</a>
        </motion.div>
      </div>
      <StatusCard />
    </section>
  );
}

function AgentNetwork() {
  return (
    <section id="agents" className="relative h-[400vh] bg-[#030303]">
      <div className="sticky top-0 flex h-screen items-center justify-center overflow-hidden px-5">
        <div className="absolute inset-0 network-topology opacity-70" />
        <div className="relative h-[72vh] w-full max-w-6xl">
          <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none">
            {agents.slice(1).map((agent, index) => (
              <motion.line key={agent.name} x1="50" y1="50" x2={parseInt(agent.x)} y2={parseInt(agent.y)} stroke="#00E5FF" strokeWidth="0.18" strokeDasharray="1 2" initial={{ pathLength: 0, opacity: 0.15 }} whileInView={{ pathLength: 1, opacity: 0.8 }} transition={{ ...spring, delay: index * 0.12 }} />
            ))}
          </svg>
          <div className="agent-center">INTELLIGENCE<br />LAYER</div>
          {agents.map((agent, index) => (
            <motion.div key={agent.name} className="agent-node" style={{ left: agent.x, top: agent.y }} initial={{ opacity: 0, scale: 0.8 }} whileInView={{ opacity: 1, scale: 1 }} transition={{ ...spring, delay: index * 0.18 }}>
              <span className="agent-pulse" />
              <h3>{agent.name}</h3>
              {agent.scans.map((item) => <p key={item}>{item}</p>)}
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}

function MarketVisualization() {
  return (
    <section className="relative flex min-h-screen items-center overflow-hidden bg-[#030303] px-5 py-24">
      <div className="market-canvas mx-auto h-[78vh] w-full max-w-7xl">
        <div className="liquidity-river river-a" />
        <div className="liquidity-river river-b" />
        <div className="vol-cloud cloud-a" />
        <div className="vol-cloud cloud-b" />
        <div className="heatmap" />
        <div className="execution-trails" />
        <div className="absolute left-6 top-6 max-w-sm">
          <p className="font-mono text-[10px] uppercase tracking-[0.24em] text-[#00E5FF]">Market visualization</p>
          <h2 className="mt-4 text-4xl font-medium tracking-[-0.04em] text-white sm:text-6xl">How an AI sees markets.</h2>
        </div>
      </div>
    </section>
  );
}

function StrategyStack() {
  return (
    <section className="relative bg-[#030303] px-5 py-28">
      <div className="mx-auto max-w-6xl">
        <h2 className="mb-16 max-w-3xl text-5xl font-medium tracking-[-0.04em] text-white sm:text-7xl">Strategy stack.</h2>
        <div className="space-y-8">
          {strategies.map(([num, name, sharpe, win, note], index) => (
            <motion.article key={name} className="strategy-card sticky p-6 sm:p-8" style={{ top: 84 + index * 18 }} initial={{ opacity: 0.75 }} whileInView={{ opacity: 1 }} transition={spring}>
              <div className="grid gap-8 lg:grid-cols-[1fr_1.2fr]">
                <div>
                  <p className="font-mono text-xs text-white/40">Card {num}</p>
                  <h3 className="mt-4 text-3xl font-medium tracking-[-0.03em] text-white sm:text-5xl">{name}</h3>
                  <div className="mt-8 grid grid-cols-2 gap-4">
                    <div><p className="text-xs uppercase tracking-[0.2em] text-white/35">Sharpe</p><p className="nums mt-2 text-3xl text-[#00FF9D]">{sharpe}</p></div>
                    <div><p className="text-xs uppercase tracking-[0.2em] text-white/35">Win rate</p><p className="nums mt-2 text-3xl text-white">{win}</p></div>
                  </div>
                  <p className="mt-8 max-w-md text-white/55">{note}</p>
                </div>
                <div className="strategy-preview"><span /><span /><span /><span /></div>
              </div>
            </motion.article>
          ))}
        </div>
      </div>
    </section>
  );
}

function DecisionEngine() {
  return (
    <section className="bg-[#030303] px-5 py-28">
      <div className="mx-auto grid max-w-6xl gap-8 lg:grid-cols-[0.8fr_1.2fr]">
        <h2 className="text-5xl font-medium tracking-[-0.04em] text-white sm:text-7xl">Decision engine.</h2>
        <div className="terminal-panel h-[520px] overflow-hidden p-5">
          <motion.div animate={{ y: [-20, -280] }} transition={{ duration: 18, repeat: Infinity, ease: "linear" }} className="space-y-4">
            {[...feed, ...feed].map(([time, message, confidence, action, execution], index) => (
              <div key={`${time}-${index}`} className="rounded-md border border-white/[0.07] bg-white/[0.025] p-4 font-mono text-xs">
                <p className="text-white/35">[{time}]</p>
                <p className="mt-3 text-sm text-white">{message}</p>
                <div className="mt-4 grid gap-2 text-white/55 sm:grid-cols-3">
                  <span>Confidence: <b className="text-[#00FF9D]">{confidence}</b></span>
                  <span>Action: <b className="text-white">{action}</b></span>
                  <span>Execution: <b className="text-[#00E5FF]">{execution}</b></span>
                </div>
              </div>
            ))}
          </motion.div>
        </div>
      </div>
    </section>
  );
}

function Trust() {
  const metrics = ["$12.4B Simulated Volume", "99.99% Uptime", "12ms Average Latency", "AES-256 Encryption", "SOC2 Infrastructure"];
  return (
    <section className="relative overflow-hidden bg-[#030303] px-5 py-32">
      <div className="absolute inset-0 network-topology opacity-50" />
      <div className="relative mx-auto max-w-7xl">
        <h2 className="max-w-5xl text-6xl font-medium leading-none tracking-[-0.05em] text-white sm:text-8xl lg:text-9xl">Built for Institutional Scale.</h2>
        <div className="mt-16 grid gap-px overflow-hidden border border-white/[0.08] bg-white/[0.08] md:grid-cols-5">
          {metrics.map((metric) => <div key={metric} className="bg-[#030303]/90 p-6 font-mono text-sm uppercase tracking-[0.12em] text-white/70">{metric}</div>)}
        </div>
      </div>
    </section>
  );
}

function FinalCta() {
  return (
    <section className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[#030303] px-5 text-center">
      <div className="convergence-field" />
      <div className="relative z-10">
        <h2 className="text-6xl font-medium tracking-[-0.05em] text-white sm:text-8xl">Let Intelligence Compound.</h2>
        <p className="mx-auto mt-6 max-w-xl text-lg text-white/60">Deploy autonomous agents that never sleep.</p>
        <a href="/signup" className="liquid-button mx-auto mt-9">Start Building</a>
      </div>
    </section>
  );
}

function SentinelFooter() {
  return (
    <footer className="relative flex h-[70vh] items-center justify-center overflow-hidden bg-[#030303]">
      <div className="data-streams" />
      <p className="select-none text-[25vw] font-medium leading-none tracking-[-0.06em] text-white/[0.04]">SENTINEL</p>
    </footer>
  );
}

export default function SentinelPage() {
  return (
    <main className="sentinel-page min-h-screen overflow-x-hidden bg-[#030303] text-[#F8F8F8]">
      <Hero />
      <AgentNetwork />
      <MarketVisualization />
      <StrategyStack />
      <DecisionEngine />
      <Trust />
      <FinalCta />
      <SentinelFooter />
    </main>
  );
}
