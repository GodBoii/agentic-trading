export default function Loading() {
  return (
    <div className="relative min-h-screen w-full bg-[#050505] flex items-center justify-center px-6 overflow-hidden">
      <div className="absolute inset-0 bg-grid-fine opacity-50" />
      <div className="absolute inset-0 bg-spotlight" />

      <div className="relative z-10 flex flex-col items-center gap-6">
        {/* Concentric pulsing rings */}
        <div className="relative h-20 w-20">
          <div className="absolute inset-0 rounded-full border border-accent/20" />
          <div className="absolute inset-2 rounded-full border border-accent/40" />
          <div className="absolute inset-4 rounded-full border border-accent/60" />
          <div className="absolute inset-[34px] rounded-full bg-accent animate-pulse-soft" />
        </div>

        <div className="flex items-center gap-2 text-[11px] font-mono uppercase tracking-[0.22em] text-ink-tertiary">
          <span className="relative flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full rounded-full bg-accent opacity-60 animate-pulse-ring" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-accent" />
          </span>
          Loading
        </div>
      </div>
    </div>
  );
}
