'use client'

import React, { useEffect, useState } from 'react';

export default function ArchitectureSVG() {
  const [pulse, setPulse] = useState(false);

  useEffect(() => {
    // Random pulses for trade execution simulation
    const interval = setInterval(() => {
      setPulse(true);
      setTimeout(() => setPulse(false), 800);
    }, 4500);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="w-full bg-[#030303] rounded-xl border border-white/5 shadow-[0_0_40px_rgba(124,58,237,0.1)] overflow-hidden relative">
      <div className="absolute inset-0 opacity-20 pointer-events-none" style={{ backgroundImage: 'radial-gradient(circle at 50% 50%, rgba(124,58,237,0.2) 0%, transparent 70%)' }}></div>
      
      {/* Title overlay */}
      <div className="absolute top-6 left-6 z-10 flex items-center gap-3">
        <div className="w-2 h-2 rounded-full bg-[#10B981] shadow-[0_0_10px_#10B981] animate-pulse"></div>
        <h3 className="font-mono text-sm tracking-widest text-[#7C3AED] uppercase">System Architecture</h3>
      </div>

      <svg viewBox="0 0 1000 500" className="w-full h-auto drop-shadow-2xl">
        <defs>
          {/* Gradients */}
          <linearGradient id="funnelGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#1a1a1a" stopOpacity="0.8" />
            <stop offset="100%" stopColor="#7C3AED" stopOpacity="0.2" />
          </linearGradient>
          <linearGradient id="beamGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#7C3AED" stopOpacity="0" />
            <stop offset="50%" stopColor="#7C3AED" stopOpacity="0.8" />
            <stop offset="100%" stopColor="#10B981" stopOpacity="1" />
          </linearGradient>
          <radialGradient id="coreGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#7C3AED" stopOpacity="0.8" />
            <stop offset="100%" stopColor="#7C3AED" stopOpacity="0" />
          </radialGradient>

          {/* Glow Filters */}
          <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="5" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
          <filter id="glow-heavy" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="12" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
          
          {/* Funnel Rings */}
          <filter id="glass" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="2" result="blur"/>
            <feColorMatrix type="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 18 -7" result="glow" />
            <feComposite in="SourceGraphic" in2="glow" operator="over"/>
          </filter>
          
          <path id="particle-path-1" d="M 50,250 C 150,150 250,250 350,250" fill="none" />
          <path id="particle-path-2" d="M 50,250 C 150,350 250,250 350,250" fill="none" />
          <path id="particle-path-3" d="M 50,250 C 200,250 250,250 350,250" fill="none" />
          <path id="particle-path-4" d="M 50,100 C 150,250 250,250 350,250" fill="none" />
          <path id="particle-path-5" d="M 50,400 C 150,250 250,250 350,250" fill="none" />
        </defs>

        {/* --- INGESTOR (Left) --- */}
        <g opacity="0.6">
          <circle cx="0" cy="250" r="150" fill="none" stroke="#333" strokeWidth="1" strokeDasharray="4 4" />
          <circle cx="50" cy="250" r="100" fill="url(#coreGlow)" opacity="0.3" />
          <text x="30" y="255" fill="#666" fontSize="12" fontFamily="monospace" transform="rotate(-90 30 255)">MKT_DATA</text>
        </g>

        {/* Particles flowing into Funnel */}
        {[1,2,3,4,5].map((i) => (
          <g key={`flow-${i}`}>
            <circle r="3" fill={i % 2 === 0 ? "#444" : "#666"}>
              <animateMotion dur={`${2+i*0.5}s`} repeatCount="indefinite" path={`M ${50},${100+i*50} C 200,${250} 250,250 350,250`} />
              <animate attributeName="opacity" values="1;0" dur={`${2+i*0.5}s`} repeatCount="indefinite" />
            </circle>
          </g>
        ))}

        {/* --- THE FUNNEL (Tier 1) --- */}
        <path d="M 200,100 L 400,220 L 400,280 L 200,400 Z" fill="url(#funnelGrad)" stroke="rgba(255,255,255,0.1)" strokeWidth="1" filter="url(#glass)" />
        <g filter="url(#glow)">
          <path d="M 250,140 Q 255,250 250,360" fill="none" stroke="#7C3AED" strokeWidth="2" opacity="0.4" />
          <path d="M 300,175 Q 303,250 300,325" fill="none" stroke="#7C3AED" strokeWidth="2" opacity="0.6" />
          <path d="M 350,205 Q 352,250 350,295" fill="none" stroke="#7C3AED" strokeWidth="2" opacity="0.8" />
          <line x1="400" y1="220" x2="400" y2="280" stroke="#7C3AED" strokeWidth="2" />
        </g>
        
        {/* Tier 1 Labels */}
        <text x="210" y="440" fill="#888" fontSize="10" fontFamily="monospace" textAnchor="middle">Sanitation</text>
        <text x="280" y="440" fill="#888" fontSize="10" fontFamily="monospace" textAnchor="middle">Liquidity</text>
        <text x="350" y="440" fill="#888" fontSize="10" fontFamily="monospace" textAnchor="middle">Momentum</text>
        <text x="400" y="440" fill="#7C3AED" fontSize="10" fontFamily="monospace" textAnchor="middle" filter="url(#glow)">Beta</text>

        {/* Golden Particles (Alpha) leaving funnel */}
        {[1,2,3].map((i) => (
          <circle key={`alpha-${i}`} r="4" fill="#7C3AED" filter="url(#glow)">
            <animateMotion dur={`${1.5+i*0.3}s`} repeatCount="indefinite" path={`M 400,${240+i*5} L 600,250`} />
            <animate attributeName="opacity" values="0;1;0" dur={`${1.5+i*0.3}s`} repeatCount="indefinite" />
          </circle>
        ))}

        {/* --- SWARM HUB (Tier 2) --- */}
        <g transform="translate(650, 250)">
          {/* Core connection lines to exchange */}
          <line x1="0" y1="0" x2="180" y2="0" stroke="url(#beamGrad)" strokeWidth={pulse ? "8" : "2"} opacity={pulse ? "1" : "0.3"} filter="url(#glow)">
            <animate attributeName="opacity" values={pulse ? "0.3;1;0.3" : "0.3"} dur="0.8s" />
          </line>

          {/* Central Aetheria Core */}
          <circle cx="0" cy="0" r="45" fill="#050505" stroke="#7C3AED" strokeWidth="2" filter="url(#glow)" />
          <polygon points="0,-20 17,10 -17,10" fill="none" stroke="#7C3AED" strokeWidth="1.5">
            <animateTransform attributeName="transform" type="rotate" from="0" to="360" dur="20s" repeatCount="indefinite" />
          </polygon>
          <polygon points="0,20 17,-10 -17,-10" fill="none" stroke="#7C3AED" strokeWidth="1.5">
            <animateTransform attributeName="transform" type="rotate" from="360" to="0" dur="20s" repeatCount="indefinite" />
          </polygon>
          <circle cx="0" cy="0" r="10" fill={pulse ? "#10B981" : "#7C3AED"} filter="url(#glow-heavy)">
            <animate attributeName="r" values="8;12;8" dur="2s" repeatCount="indefinite" />
          </circle>
          <text x="0" y="5" fill="#fff" fontSize="10" fontFamily="monospace" textAnchor="middle" fontWeight="bold">AETHERIA</text>
          
          {/* Orbiting Agents */}
          <g>
            <animateTransform attributeName="transform" type="rotate" from="0" to="360" dur="60s" repeatCount="indefinite" />
            
            {/* Agent Nodes */}
            <circle cx="0" cy="0" r="120" fill="none" stroke="rgba(124,58,237,0.1)" strokeWidth="1" strokeDasharray="5 5" />
            
            {[
              { id: 'Chronos', angle: 0, color: '#A78BFA' },
              { id: 'Athena', angle: 60, color: '#34D399' },
              { id: 'Quant', angle: 120, color: '#60A5FA' },
              { id: 'Apollo', angle: 180, color: '#FCD34D' },
              { id: 'Hermes', angle: 240, color: '#F472B6' },
              { id: 'Strat', angle: 300, color: '#F87171' }
            ].map((agent, i) => {
              const x = Math.cos(agent.angle * Math.PI / 180) * 120;
              const y = Math.sin(agent.angle * Math.PI / 180) * 120;
              return (
                <g key={`agent-${i}`} transform={`translate(${x}, ${y}) rotate(${-agent.angle})`}>
                  {/* Rotation counter-balance is handled implicitly but for labels it needs reverse transform */}
                  <g>
                    <animateTransform attributeName="transform" type="rotate" from="0" to="-360" dur="60s" repeatCount="indefinite" />
                    
                    {/* Beam to core */}
                    <line x1="0" y1="0" x2={-x} y2={-y} stroke={agent.color} strokeWidth="1" opacity="0.3" strokeDasharray="2 4">
                       <animate attributeName="stroke-dashoffset" values="0;-20" dur="1s" repeatCount="indefinite" />
                    </line>

                    <circle r="18" fill="#111" stroke={agent.color} strokeWidth="1.5" filter="url(#glow)" />
                    <circle r="4" fill={agent.color} filter="url(#glow)">
                      <animate attributeName="opacity" values="0.4;1;0.4" dur={`${1.5 + (i * 0.2)}s`} repeatCount="indefinite" />
                    </circle>
                    <text x="0" y="28" fill="#aaa" fontSize="10" fontFamily="monospace" textAnchor="middle">{agent.id}</text>
                  </g>
                </g>
              );
            })}
          </g>
        </g>

        {/* --- EXECUTION (Right) --- */}
        <g transform="translate(850, 250)">
          <rect x="-10" y="-80" width="80" height="160" rx="4" fill="#080808" stroke="#333" strokeWidth="2" />
          <text x="30" y="-60" fill="#555" fontSize="12" fontFamily="monospace" textAnchor="middle" fontWeight="bold">DHAN API</text>
          
          <g fill="#222">
             <rect x="0" y="-40" width="60" height="10" rx="2" />
             <rect x="0" y="-20" width="60" height="10" rx="2" />
             <rect x="0" y="0" width="60" height="10" rx="2" />
             <rect x="0" y="20" width="60" height="10" rx="2" />
             <rect x="0" y="40" width="60" height="10" rx="2" />
          </g>

          {/* Trade Execution Flash */}
          <circle cx="30" cy="5" r={pulse ? "80" : "0"} fill="#10B981" opacity={pulse ? "0" : "0"} style={{transition: "all 0.5s ease-out"}}>
            {pulse && <animate attributeName="opacity" values="0.4;0" dur="0.8s" />}
            {pulse && <animate attributeName="r" values="10;80" dur="0.8s" />}
          </circle>
          
          {pulse && (
            <text x="30" y="70" fill="#10B981" fontSize="14" fontFamily="monospace" textAnchor="middle" filter="url(#glow)" fontWeight="bold">
              EXECUTE
              <animate attributeName="opacity" values="1;0" dur="2s" />
              <animate attributeName="y" values="70;60" dur="2s" />
            </text>
          )}
        </g>
        
        {/* Data lines background */}
        <g stroke="rgba(255,255,255,0.02)" strokeWidth="1">
          <line x1="0" y1="100" x2="1000" y2="100" />
          <line x1="0" y1="400" x2="1000" y2="400" />
          <line x1="200" y1="0" x2="200" y2="500" />
          <line x1="800" y1="0" x2="800" y2="500" />
        </g>

      </svg>
      
      {/* Legend / Overlay info */}
      <div className="absolute bottom-6 left-6 z-10 hidden md:block">
        <div className="flex flex-col gap-2 font-mono text-xs text-white/50 bg-black/40 p-4 rounded-lg backdrop-blur-md border border-white/5">
          <div className="flex items-center gap-2"><div className="w-2 h-2 rounded-full bg-[#333]"></div> Tier 1: Raw Volume Scanner</div>
          <div className="flex items-center gap-2"><div className="w-2 h-2 rounded-full bg-[#7C3AED]"></div> Tier 2: Selected Candidates</div>
          <div className="flex items-center gap-2"><div className="w-2 h-2 rounded-full bg-[#10B981]"></div> Execution: Positive Confidence</div>
        </div>
      </div>
    </div>
  );
}
