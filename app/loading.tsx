import { Shimmer } from '@/components/motion/shimmer'
import { ThinkingOrb } from '@/components/motion/thinking-orb'

/**
 * Route-level loading state.
 *
 * Motion. The concentric ring stack and its `pulse-soft` / `pulse-ring`
 * animations are replaced with a 64px thinking orb and a shimmering label.
 *
 * The rings said only "wait" — three static borders around a pulsing dot, at a
 * size that dominated the viewport. The orb says the app is working, at a size
 * tuned for a standalone indicator, and the shimmer keeps the label alive
 * without a second competing animation beside it. Both derive from the same
 * shared motion clock, so they cannot drift out of phase with each other the
 * way two independently-timed pulses did.
 */
export default function Loading() {
    return (
        <div className="relative flex min-h-screen w-full items-center justify-center overflow-hidden bg-[#050505] px-6">
            <div className="absolute inset-0 bg-grid-fine opacity-50" />
            <div className="absolute inset-0 bg-spotlight" />

            <div className="relative z-10 flex flex-col items-center gap-6">
                <ThinkingOrb state="working" size={64} label="Loading" className="text-accent" />
                <Shimmer className="font-mono text-[11px] uppercase tracking-[0.22em]">Loading</Shimmer>
            </div>
        </div>
    )
}
