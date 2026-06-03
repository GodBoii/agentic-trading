"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

export default function Nav() {
  const [scrolled, setScrolled] = useState(false);
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <motion.header
      initial={{ y: -32, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1], delay: 0.1 }}
      className="fixed top-0 inset-x-0 z-50 px-4 sm:px-6"
    >
      <div
        className={`mx-auto max-w-7xl mt-4 transition-all duration-700 ease-out-expo rounded-full border ${
          scrolled
            ? "bg-[#0a0a0c]/80 backdrop-blur-xl border-white/10"
            : "bg-transparent border-transparent"
        }`}
      >
        <div className="flex items-center justify-between px-5 sm:px-6 py-3">
          {/* Logo */}
          <Link href="/" className="group flex items-center gap-2.5">
            <div className="relative h-7 w-7">
              <div className="absolute inset-0 rounded-full bg-gradient-to-br from-accent to-success opacity-80 blur-md group-hover:opacity-100 transition-opacity" />
              <div className="absolute inset-[3px] rounded-full bg-[#0a0a0c] flex items-center justify-center">
                <div className="h-1.5 w-1.5 rounded-full bg-white" />
              </div>
            </div>
            <span className="text-[15px] font-medium tracking-[-0.02em] text-white">
              Aetheria
            </span>
            <span className="hidden sm:inline-block text-[10px] font-mono uppercase tracking-[0.2em] text-white/40 pl-2 border-l border-white/10 ml-1">
              AI
            </span>
          </Link>

          {/* Center links */}
          <nav className="hidden md:flex items-center gap-8">
            {[
              { label: "System", href: "#system" },
              { label: "Agents", href: "#agents" },
              { label: "Strategies", href: "#strategies" },
              { label: "Performance", href: "#performance" },
            ].map((item) => (
              <a
                key={item.label}
                href={item.href}
                className="text-[13px] text-white/60 hover:text-white transition-colors duration-300 tracking-[-0.01em]"
              >
                {item.label}
              </a>
            ))}
          </nav>

          {/* CTAs */}
          <div className="flex items-center gap-2">
            <Link
              href="/login"
              className="hidden sm:inline-flex text-[13px] text-white/70 hover:text-white transition-colors px-3 py-1.5 tracking-[-0.01em]"
            >
              Sign in
            </Link>
            <Link
              href="/signup"
              className="relative inline-flex items-center gap-1.5 text-[13px] font-medium text-black bg-white hover:bg-white/90 rounded-full px-4 py-1.5 transition-all duration-300 tracking-[-0.01em] hover:shadow-[0_0_24px_rgba(255,255,255,0.15)]"
            >
              Launch Agent
              <span className="text-[10px]">→</span>
            </Link>
          </div>
        </div>
      </div>
    </motion.header>
  );
}
