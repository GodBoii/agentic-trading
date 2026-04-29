'use client'

import React, { useEffect, useState } from 'react';

export default function ArchitectureSVG() {
  const [pulse, setPulse] = useState(false);

  useEffect(() => {
    // Random pulses for trade execution simulation
    const interval = setInterval(() => {
      setPulse(true);
      setTimeout(() => setPulse(false), 900);
    }, 4000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="w-full bg-[#030303] rounded-2xl border border-white/10 shadow-[0_0_40px_rgba(79,70,229,0.15)] overflow-x-auto relative">
      {/* Background grid pattern */}
      <svg viewBox="0 0 1300 700" className="w-full h-auto min-w-[1100px] drop-shadow-2xl">
        <defs>
          <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(255,255,255,0.02)" strokeWidth="1" />
          </pattern>
          
          <radialGradient id="dataGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#4F46E5" stopOpacity="0.8" />
            <stop offset="100%" stopColor="#4F46E5" stopOpacity="0" />
          </radialGradient>
          
          <linearGradient id="beamGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#10B981" stopOpacity="0.2" />
            <stop offset="100%" stopColor="#10B981" stopOpacity="1" />
          </linearGradient>

          <filter id="glow-violet" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="8" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
          
          <filter id="glow-cyan" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="8" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>

          <filter id="glow-emerald" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="8" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>

          <path id="report-path" d="M 910 350 L 1050 350" />
        </defs>

        <rect width="1300" height="700" fill="url(#grid)" />

        {/* --- 1. BSE UNIVERSE DATA SOURCE --- */}
        <g transform="translate(80, 350)">
          <circle cx="0" cy="0" r="50" fill="none" stroke="#444" strokeWidth="2" strokeDasharray="4 6">
             <animateTransform attributeName="transform" type="rotate" from="0" to="360" dur="20s" repeatCount="indefinite" />
          </circle>
          <circle cx="0" cy="0" r="30" fill="rgba(80,80,80,0.1)" stroke="#555" strokeWidth="1" />
          <text x="0" y="-5" fill="#aaa" fontSize="16" textAnchor="middle" fontFamily="monospace" fontWeight="bold">BSE</text>
          <text x="0" y="15" fill="#666" fontSize="12" textAnchor="middle" fontFamily="monospace">5300 Stocks</text>
        </g>


        {/* --- 2. THE AETHERIA STOCK ANALYZER (TOP CONTAINER) --- */}
        <rect x="220" y="50" width="450" height="250" rx="12" fill="rgba(124,58,237,0.02)" stroke="#7C3AED" strokeWidth="1" strokeOpacity="0.4" />
        <text x="445" y="80" fill="#A78BFA" fontSize="16" textAnchor="middle" fontFamily="monospace" fontWeight="bold" filter="url(#glow-violet)">
          THE AETHERIA STOCK ANALYZER
        </text>

        {/* Flow connectors into Analyzer */}
        <path d="M 130 350 Q 180 180 240 180" fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="2" />
        <line x1="340" y1="180" x2="410" y2="180" stroke="rgba(255,255,255,0.1)" strokeWidth="2" />
        <line x1="490" y1="180" x2="550" y2="180" stroke="rgba(255,255,255,0.1)" strokeWidth="2" />

        {/* Flowing Particles from BSE to Stage 1 */}
        {[...Array(12)].map((_, i) => (
          <circle key={`in-${i}`} r="2.5" fill="#888">
            <animateMotion dur={`${2 + (i % 3) * 0.5}s`} begin={`${i * 0.2}s`} repeatCount="indefinite" path="M 130 350 Q 180 180 240 180" />
            <animate attributeName="opacity" values="0;1;1;0" dur={`${2 + (i % 3) * 0.5}s`} repeatCount="indefinite" />
          </circle>
        ))}

        {/* Stage 1: Universe Scanner */}
        <g transform="translate(240, 120)">
           <rect x="0" y="0" width="100" height="120" rx="8" fill="#0A0A0A" stroke="#555" strokeWidth="1.5" />
           <line x1="10" y1="25" x2="90" y2="25" stroke="#333" strokeWidth="1" />
           <text x="50" y="18" fill="#aaa" fontSize="11" textAnchor="middle" fontFamily="monospace">STAGE 1</text>
           <text x="50" y="55" fill="#fff" fontSize="14" textAnchor="middle" fontFamily="monospace" fontWeight="bold">Universe</text>
           <text x="50" y="75" fill="#fff" fontSize="14" textAnchor="middle" fontFamily="monospace" fontWeight="bold">Scanner</text>
           <text x="50" y="105" fill="#7C3AED" fontSize="10" textAnchor="middle" fontFamily="monospace" filter="url(#glow-violet)">~300 STOCKS</text>
           
           {/* Discarded Particles Animation */}
           {[...Array(8)].map((_, i) => (
              <circle key={`drop1-${i}`} r="2" fill="#555">
                <animateMotion dur="2s" begin={`${i * 0.3}s`} repeatCount="indefinite" path="M 50 120 Q 50 180 20 220" />
                <animate attributeName="opacity" values="1;0" dur="2s" begin={`${i * 0.3}s`} repeatCount="indefinite" />
              </circle>
           ))}
        </g>

        {/* Particles from Stage 1 to Stage 2 */}
        {[...Array(6)].map((_, i) => (
          <circle key={`mid-${i}`} r="3" fill="#A78BFA" filter="url(#glow-violet)">
            <animateMotion dur="1.5s" begin={`${i * 0.3}s`} repeatCount="indefinite" path="M 340 180 L 410 180" />
          </circle>
        ))}

        {/* Stage 2: Momentum Ignition */}
        <g transform="translate(410, 130)">
           <rect x="0" y="0" width="80" height="100" rx="8" fill="#0A0A0A" stroke="#7C3AED" strokeWidth="1.5" filter="url(#glow-violet)" />
           <line x1="10" y1="20" x2="70" y2="20" stroke="#444" strokeWidth="1" />
           <text x="40" y="14" fill="#A78BFA" fontSize="10" textAnchor="middle" fontFamily="monospace">STAGE 2</text>
           <text x="40" y="45" fill="#fff" fontSize="11" textAnchor="middle" fontFamily="monospace" fontWeight="bold">Momentum</text>
           <text x="40" y="60" fill="#fff" fontSize="11" textAnchor="middle" fontFamily="monospace" fontWeight="bold">Ignition</text>
           <text x="40" y="85" fill="#10B981" fontSize="10" textAnchor="middle" fontFamily="monospace">3-5 STOCKS</text>

           {/* Discarded Particles Animation */}
           {[...Array(4)].map((_, i) => (
              <circle key={`drop2-${i}`} r="2" fill="#7C3AED">
                <animateMotion dur="1.5s" begin={`${i * 0.4}s`} repeatCount="indefinite" path="M 40 100 Q 40 150 60 180" />
                <animate attributeName="opacity" values="0.8;0" dur="1.5s" begin={`${i * 0.4}s`} repeatCount="indefinite" />
              </circle>
           ))}
        </g>

        {/* Particles from Stage 2 to Monitor */}
        {[...Array(3)].map((_, i) => (
          <circle key={`mon-in-${i}`} r="3" fill="#10B981" filter="url(#glow-emerald)">
            <animateMotion dur="1s" begin={`${i * 0.5}s`} repeatCount="indefinite" path="M 490 180 L 550 180" />
          </circle>
        ))}

        {/* Monitor: Hard Liquidity Gate */}
        <g transform="translate(550, 115)">
           <rect x="0" y="0" width="100" height="130" rx="50" fill="rgba(16,185,129,0.05)" stroke="#10B981" strokeWidth="1.5" />
           
           <text x="50" y="20" fill="#10B981" fontSize="10" textAnchor="middle" fontFamily="monospace" fontWeight="bold">MONITOR</text>
           <text x="50" y="115" fill="#34D399" fontSize="9" textAnchor="middle" fontFamily="monospace">Hard Liquidity Gate</text>

           {/* Orbiting Radar inside Monitor */}
           <g transform="translate(50, 60)">
              <circle cx="0" cy="0" r="28" fill="none" stroke="#10B981" strokeWidth="1" strokeDasharray="3 3" opacity="0.5" />
              <path d="M 0 0 L 28 0 A 28 28 0 0 1 0 28 Z" fill="rgba(16,185,129,0.2)">
                 <animateTransform attributeName="transform" type="rotate" from="0" to="360" dur="1.5s" repeatCount="indefinite" />
              </path>
              
              {/* Captured Stocks (The 3-5 candidates) */}
              <g>
                 <animateTransform attributeName="transform" type="rotate" from="360" to="0" dur="4s" repeatCount="indefinite" />
                 <circle cx="15" cy="-8" r="4" fill="#fff" filter="url(#glow-emerald)" />
                 <circle cx="-12" cy="12" r="3.5" fill="#fff" filter="url(#glow-emerald)" />
                 <circle cx="-6" cy="-18" r="4" fill="#fff" filter="url(#glow-emerald)" />
              </g>
           </g>
        </g>


        {/* --- 3. REGIME MODULE (BOTTOM CONTAINER) --- */}
        <path d="M 130 350 Q 180 510 240 510" fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="2" />
        {[...Array(5)].map((_, i) => (
          <circle key={`reg-in-${i}`} r="2" fill="#06B6D4">
            <animateMotion dur="2.5s" begin={`${i * 0.5}s`} repeatCount="indefinite" path="M 130 350 Q 180 510 240 510" />
            <animate attributeName="opacity" values="0;0.8;0" dur="2.5s" begin={`${i * 0.5}s`} repeatCount="indefinite" />
          </circle>
        ))}

        <rect x="220" y="380" width="450" height="230" rx="12" fill="rgba(6,182,212,0.02)" stroke="#06B6D4" strokeWidth="1" strokeOpacity="0.4" />
        <text x="445" y="415" fill="#06B6D4" fontSize="16" textAnchor="middle" fontFamily="monospace" fontWeight="bold" filter="url(#glow-cyan)">
          REGIME (MARKET CONTEXT)
        </text>

        {/* Regime Live HUD Data */}
        <g transform="translate(250, 440)">
           <rect x="0" y="0" width="220" height="140" rx="6" fill="#050505" stroke="#111" strokeWidth="2" />
           <g transform="translate(15, 25)">
              <text x="0" y="0" fill="#06B6D4" fontSize="11" fontFamily="monospace" fontWeight="bold">{'>'} ANALYZING ENTIRE MARKET...</text>
              <line x1="0" y1="8" x2="190" y2="8" stroke="#222" strokeWidth="1" />
              <text x="0" y="25" fill="#888" fontSize="11" fontFamily="monospace">market_regime: <tspan fill="#10B981" fontWeight="bold">TREND</tspan></text>
              <text x="0" y="45" fill="#888" fontSize="11" fontFamily="monospace">trade_perm:    <tspan fill="#10B981" fontWeight="bold">ALLOWED</tspan></text>
              <text x="0" y="65" fill="#888" fontSize="11" fontFamily="monospace">pref_style:    <tspan fill="#FCD34D" fontWeight="bold">TREND_FOLLOW</tspan></text>
              <text x="0" y="85" fill="#888" fontSize="11" fontFamily="monospace">size_mult:     <tspan fill="#F472B6" fontWeight="bold">1.5X</tspan></text>
              <text x="0" y="105" fill="#888" fontSize="11" fontFamily="monospace">max_pos:       <tspan fill="#fff" fontWeight="bold">3</tspan></text>
           </g>
        </g>

        {/* Regime Waveform Scanner */}
        <g transform="translate(500, 440)">
           <rect x="0" y="0" width="140" height="140" rx="6" fill="#050505" stroke="#111" strokeWidth="2" />
           {/* Grid lines */}
           <line x1="0" y1="35" x2="140" y2="35" stroke="#222" strokeDasharray="2 2" />
           <line x1="0" y1="70" x2="140" y2="70" stroke="#222" strokeDasharray="2 2" />
           <line x1="0" y1="105" x2="140" y2="105" stroke="#222" strokeDasharray="2 2" />
           
           <path d="M 0,70 Q 17,20 35,70 T 70,70 T 105,70 T 140,70" fill="none" stroke="#06B6D4" strokeWidth="2" filter="url(#glow-cyan)">
              <animate attributeName="d" 
                       values="M 0,70 Q 17,20 35,70 T 70,70 T 105,70 T 140,70;
                               M 0,70 Q 17,120 35,70 T 70,70 T 105,70 T 140,70;
                               M 0,70 Q 17,20 35,70 T 70,70 T 105,70 T 140,70" 
                       dur="2s" repeatCount="indefinite" />
           </path>
           <circle cx="140" cy="70" r="3" fill="#06B6D4" />
        </g>


        {/* --- DATA STREAMS TO DATA ANALYZER --- */}
        {/* Stream from Monitor to Data Analyzer */}
        <path d="M 650 180 Q 850 180 850 290" fill="none" stroke="rgba(16,185,129,0.3)" strokeWidth="3" strokeDasharray="8 8">
           <animate attributeName="stroke-dashoffset" values="32;0" dur="1s" repeatCount="indefinite" />
        </path>
        <text x="730" y="170" fill="#10B981" fontSize="10" fontFamily="monospace">Filtered Tickers</text>

        {/* Stream from Regime to Data Analyzer */}
        <path d="M 670 495 Q 850 495 850 410" fill="none" stroke="rgba(6,182,212,0.3)" strokeWidth="3" strokeDasharray="8 8">
           <animate attributeName="stroke-dashoffset" values="32;0" dur="1s" repeatCount="indefinite" />
        </path>
        <text x="730" y="515" fill="#06B6D4" fontSize="10" fontFamily="monospace">Context / Logic Limits</text>


        {/* --- 4. AETHERIA DATA ANALYZER --- */}
        {/* Hexagon shape around core */}
        <g transform="translate(850, 350)">
           <polygon points="0,-60 52,-30 52,30 0,60 -52,30 -52,-30" fill="rgba(79,70,229,0.05)" stroke="#4F46E5" strokeWidth="2" filter="url(#glow-violet)" />
           
           <circle cx="0" cy="0" r="35" fill="#0A0A0A" stroke="#4F46E5" strokeWidth="2" />
           <circle cx="0" cy="0" r="15" fill="#4F46E5" filter="url(#glow-violet)">
              <animate attributeName="r" values="10;18;10" dur="1.5s" repeatCount="indefinite" />
           </circle>

           {/* Inner AI Nodes communicating */}
           {[0, 72, 144, 216, 288].map((angle, i) => {
              const x = Math.cos(angle * Math.PI / 180) * 25;
              const y = Math.sin(angle * Math.PI / 180) * 25;
              return (
                <circle key={`node-${i}`} cx={x} cy={y} r="3" fill="#A78BFA" opacity="0.8">
                   <animate attributeName="opacity" values="0.2;1;0.2" dur={`${1 + i*0.2}s`} repeatCount="indefinite" />
                </circle>
              )
           })}

           <text x="0" y="85" fill="#4F46E5" fontSize="14" textAnchor="middle" fontFamily="monospace" fontWeight="bold">AETHERIA</text>
           <text x="0" y="105" fill="#4F46E5" fontSize="14" textAnchor="middle" fontFamily="monospace" fontWeight="bold">DATA ANALYZER</text>
        </g>


        {/* --- 5. THE REPORT PIPELINE --- */}
        <path d="M 910 350 L 1050 350" fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="2" />
        <g>
           <animateMotion dur="2s" repeatCount="indefinite">
               <mpath href="#report-path" />
           </animateMotion>
           <rect x="-16" y="-20" width="32" height="40" rx="3" fill="#111" stroke="#A78BFA" strokeWidth="1.5" filter="url(#glow-violet)" />
           <line x1="-8" y1="-8" x2="8" y2="-8" stroke="#A78BFA" strokeWidth="2" />
           <line x1="-8" y1="2" x2="8" y2="2" stroke="#A78BFA" strokeWidth="2" />
           <line x1="-8" y1="12" x2="2" y2="12" stroke="#A78BFA" strokeWidth="2" />
           <text x="0" y="-28" fill="#A78BFA" fontSize="10" textAnchor="middle" fontFamily="monospace" fontWeight="bold">Report</text>
        </g>


        {/* --- 6. AETHERIA TRADER --- */}
        {/* Diamond shape around core */}
        <g transform="translate(1100, 350)">
           <polygon points="0,-50 50,0 0,50 -50,0" fill="rgba(16,185,129,0.05)" stroke="#10B981" strokeWidth="2" filter="url(#glow-emerald)" />
           
           <circle cx="0" cy="0" r="30" fill="#0A0A0A" stroke="#10B981" strokeWidth="2" />
           <rect x="-10" y="-10" width="20" height="20" rx="4" fill="#10B981" filter="url(#glow-emerald)">
               <animateTransform attributeName="transform" type="rotate" from="0" to="360" dur="4s" repeatCount="indefinite" />
           </rect>

           <text x="0" y="85" fill="#10B981" fontSize="14" textAnchor="middle" fontFamily="monospace" fontWeight="bold">AETHERIA</text>
           <text x="0" y="105" fill="#10B981" fontSize="14" textAnchor="middle" fontFamily="monospace" fontWeight="bold">TRADER</text>
        </g>


        {/* --- 7. DHAN API EXECUTION --- */}
        {/* Firing Beam */}
        <path d="M 1150 350 L 1220 350" fill="none" stroke="url(#beamGrad)" strokeWidth={pulse ? 10 : 2} opacity={pulse ? 1 : 0} filter="url(#glow-emerald)">
            {pulse && <animate attributeName="stroke-width" values="2;10;2" dur="0.8s" />}
            {pulse && <animate attributeName="opacity" values="0;1;0" dur="0.8s" />}
        </path>
        
        {pulse && (
           <text x="1185" y="335" fill="#10B981" fontSize="14" textAnchor="middle" fontFamily="monospace" fontWeight="bold" filter="url(#glow-emerald)">
               EXECUTE
               <animate attributeName="opacity" values="1;0" dur="0.8s" />
           </text>
        )}

        <g transform="translate(1220, 300)">
           <rect x="0" y="0" width="50" height="100" rx="4" fill="#0A0A0A" stroke="#333" strokeWidth="2" />
           <text x="25" y="-15" fill="#ddd" fontSize="14" textAnchor="middle" fontFamily="monospace" fontWeight="bold">DHAN</text>
           <text x="25" y="-30" fill="#aaa" fontSize="10" textAnchor="middle" fontFamily="monospace">Broker</text>
           
           {/* Server Lights */}
           {[10, 30, 50, 70, 90].map((y, i) => (
              <g key={`dhan-srv-${i}`}>
                 <line x1="10" y1={y} x2="40" y2={y} stroke="#222" strokeWidth="6" strokeLinecap="round" />
                 <circle cx="15" cy={y} r="2" fill={i % 2 === 0 ? "#10B981" : "#06B6D4"} opacity="0.8">
                    <animate attributeName="opacity" values="0.2;1;0.2" dur={`${Math.random() + 0.5}s`} repeatCount="indefinite" />
                 </circle>
              </g>
           ))}
        </g>

      </svg>
    </div>
  );
}
