import React from 'react';
import Link from 'next/link';

export default function Footer() {
  return (
    <footer className="w-full bg-[#030303] border-t border-white/5 relative overflow-hidden mt-12 z-50">
      {/* Top Gradient Line */}
      <div className="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-[#7C3AED]/50 to-transparent"></div>

      <div className="max-w-7xl mx-auto px-6 lg:px-8 py-12 relative z-10">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-12">
          
          {/* Column 1: Identity */}
          <div className="flex flex-col space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-3 h-3 bg-[#7C3AED] shadow-[0_0_10px_#7C3AED] rounded-sm"></div>
              <h2 className="text-xl font-bold text-white tracking-widest font-sans uppercase">Aetheria AI</h2>
            </div>
            <p className="text-white/60 font-mono text-sm leading-relaxed max-w-xs mt-4">
              Advanced Agentic Trading Neural System. Engineered for precision and alpha.
            </p>
            <div className="mt-4 pt-4 border-t border-white/10">
              <span className="text-white/40 font-mono text-xs block mb-1">ARCHITECT & LEAD ENGINEER</span>
              <span className="text-[#10B981] font-mono font-bold tracking-wide">Prajwal Ghadge</span>
            </div>
          </div>

          {/* Column 2: External Comm Links */}
          <div className="flex flex-col space-y-4 md:pl-10">
             <h3 className="text-white/40 font-mono text-xs uppercase tracking-widest mb-2 flex items-center gap-2">
                 <span>{`//`}</span> EXTERNAL_UPLINKS
             </h3>
             <ul className="space-y-3 font-mono text-sm">
                 <li>
                     <Link href="https://aetheriaai.online" target="_blank" className="group flex items-center gap-2 text-white/70 hover:text-[#7C3AED] transition-colors">
                        <span className="opacity-0 group-hover:opacity-100 transition-opacity text-[#7C3AED]">&gt;</span> Official Site: aetheriaai.online
                     </Link>
                 </li>
                 <li>
                     <Link href="https://github.com/GodBoii" target="_blank" className="group flex items-center gap-2 text-white/70 hover:text-white transition-colors">
                        <span className="opacity-0 group-hover:opacity-100 transition-opacity text-white">&gt;</span> GitHub: @GodBoii
                     </Link>
                 </li>
                 <li>
                     <Link href="https://instagram.com/prajwal_._7" target="_blank" className="group flex items-center gap-2 text-white/70 hover:text-[#F472B6] transition-colors">
                        <span className="opacity-0 group-hover:opacity-100 transition-opacity text-[#F472B6]">&gt;</span> Instagram: @prajwal_._7
                     </Link>
                 </li>
             </ul>
          </div>

          {/* Column 3: Contact & Status */}
          <div className="flex flex-col space-y-4 md:pl-10">
              <h3 className="text-white/40 font-mono text-xs uppercase tracking-widest mb-2 flex items-center gap-2">
                 <span>{`//`}</span> SYSTEM_COMMS
             </h3>
             
             <div className="bg-[#080808] border border-white/5 p-4 rounded-lg">
                <div className="flex items-center gap-2 mb-3">
                    <div className="w-2 h-2 rounded-full bg-[#10B981] animate-pulse"></div>
                    <span className="text-[#10B981] font-mono text-xs font-bold">SYSTEM ONLINE</span>
                </div>
                
                <a href="mailto:aetheriaai1@gmail.com" className="block text-white/80 font-mono text-sm hover:text-[#10B981] transition-colors truncate">
                    aetheriaai1@gmail.com
                </a>
             </div>
          </div>

        </div>

        {/* Bottom Bar */}
        <div className="mt-12 pt-6 border-t border-white/5 flex flex-col md:flex-row justify-between items-center gap-4">
            <p className="text-white/30 font-mono text-xs">
                © {new Date().getFullYear()} Aetheria AI. All systems operational.
            </p>
            <div className="flex items-center gap-2 text-white/20 font-mono text-[10px]">
                <span>[ TERMINAL_ID: AETH-001 ]</span>
                <span className="animate-pulse">_</span>
            </div>
        </div>
      </div>
    </footer>
  );
}
