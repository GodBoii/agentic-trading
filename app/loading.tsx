import { Shimmer } from '@/components/motion/shimmer'
import { ThinkingOrb } from '@/components/motion/thinking-orb'

/**
 * Route-level loading state.
 *
 * Motion. A 64px thinking orb and a shimmering label, replacing a concentric
 * ring stack driven by `pulse-soft` and `pulse-ring`.
 *
 * The rings said only "wait" — three static borders around a pulsing dot, at a
 * size that dominated the viewport. The orb says the app is working, at a size
 * tuned for a standalone indicator, and the shimmer keeps the label alive
 * without a second competing animation beside it. Both derive from the same
 * shared motion clock, so they cannot drift out of phase the way two
 * independently-timed pulses did.
 */
export default function Loading() {
    return (
        <div className="relative flex min-h-[100dvh] w-full items-center justify-center overflow-hidden bg-canvas px-6">
            <div aria-hidden className="pointer-events-none absolute inset-0 bg-grid-fine bg-grid-fade" />

            <div className="relative z-[2] flex flex-col items-center gap-5">
                <ThinkingOrb state="working" size={64} label="Loading" className="text-accent" />
                <Shimmer className="font-mono text-[11px] uppercase tracking-[0.2em]">Loading</Shimmer>
            </div>
        </div>
    )
}
