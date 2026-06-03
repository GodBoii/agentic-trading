"use client";

import { useEffect } from "react";
import Link from "next/link";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="relative min-h-screen w-full bg-[#050505] flex items-center justify-center px-6 overflow-hidden">
      <div className="absolute inset-0 bg-grid-fine opacity-50" />
      <div className="absolute -top-40 left-1/2 -translate-x-1/2 w-[600px] h-[600px] bg-danger/[0.05] rounded-full blur-[120px] pointer-events-none" />

      <div className="relative z-10 w-full max-w-md text-center">
        <div className="inline-flex items-center gap-2 mb-6">
          <span className="h-px w-8 bg-danger" />
          <span className="text-[11px] font-mono uppercase tracking-[0.22em] text-danger">
            Runtime error
          </span>
          <span className="h-px w-8 bg-danger" />
        </div>

        <h1 className="font-display text-[44px] sm:text-[56px] text-white tracking-[-0.035em] leading-[0.95] mb-4">
          Something broke.
        </h1>
        <p className="text-[14px] text-ink-secondary leading-relaxed mb-8 max-w-sm mx-auto">
          We hit an unexpected condition. The error has been logged. You can
          try again or return to the homepage.
        </p>

        {error.message && (
          <div className="mb-8 rounded-lg border border-danger/30 bg-danger/[0.08] px-4 py-3 text-left">
            <p className="text-[12px] font-mono text-danger break-all">
              {error.message}
            </p>
          </div>
        )}

        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <button
            onClick={() => reset()}
            className="inline-flex items-center justify-center gap-2 rounded-full bg-white px-5 py-3 text-[14px] font-medium text-black transition-all duration-500 ease-out-expo hover:-translate-y-0.5 hover:shadow-[0_0_24px_rgba(255,255,255,0.15)]"
          >
            <span>Try again</span>
          </button>
          <Link
            href="/"
            className="inline-flex items-center justify-center gap-2 rounded-full border border-line bg-white/[0.02] backdrop-blur-sm px-5 py-3 text-[14px] font-medium text-white transition-all duration-500 ease-out-expo hover:bg-white/[0.06] hover:border-white/20"
          >
            <span>Go home</span>
          </Link>
        </div>
      </div>
    </div>
  );
}
