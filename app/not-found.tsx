import Link from "next/link";

export default function NotFound() {
  return (
    <div className="relative min-h-screen w-full bg-[#050505] flex items-center justify-center px-6 overflow-hidden">
      <div className="absolute inset-0 bg-grid-fine opacity-50" />
      <div className="absolute -top-40 left-1/2 -translate-x-1/2 w-[800px] h-[800px] bg-accent/[0.04] rounded-full blur-[140px] pointer-events-none" />

      <div className="relative z-10 w-full max-w-lg text-center">
        <div className="inline-flex items-center gap-2 mb-6">
          <span className="h-px w-8 bg-accent" />
          <span className="text-[11px] font-mono uppercase tracking-[0.22em] text-accent">
            404 · Not found
          </span>
          <span className="h-px w-8 bg-accent" />
        </div>

        <h1 className="font-display text-[120px] sm:text-[180px] text-white tracking-[-0.05em] leading-[0.9] mb-2">
          4
          <span className="font-serif-italic text-white/60">0</span>4
        </h1>
        <h2 className="font-display text-[24px] sm:text-[28px] text-white tracking-[-0.025em] mb-3">
          Lost in the market.
        </h2>
        <p className="text-[14px] text-ink-secondary leading-relaxed mb-10 max-w-sm mx-auto">
          The page you&apos;re looking for doesn&apos;t exist — or it has been
          moved to a new position.
        </p>

        <Link
          href="/"
          className="inline-flex items-center justify-center gap-2 rounded-full bg-white px-5 py-3 text-[14px] font-medium text-black transition-all duration-500 ease-out-expo hover:-translate-y-0.5 hover:shadow-[0_0_24px_rgba(255,255,255,0.15)]"
        >
          <span>Return home</span>
          <span>→</span>
        </Link>
      </div>
    </div>
  );
}
