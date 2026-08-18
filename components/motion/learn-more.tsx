'use client'

import { cn } from '@/lib/cn'

/**
 * Recipe 24 — learn-more hover.
 *
 * On hover the chevron slides toward the reading direction while its two arms
 * rotate apart about the apex, opening from a chevron into a full arrow. The
 * out clock matches the in clock here, both on the smooth curve.
 *
 * Replaces the literal `→` glyphs used on the landing and auth CTAs. A text
 * arrow renders at a different weight and baseline in every font on the page,
 * cannot be animated beyond a crude translate, and inherits font kerning it
 * has no business inheriting. Two `<path>`s rotating about a shared origin
 * give the same affordance with real geometry.
 *
 * Hover-only by design: keyboard focus and touch see the resting chevron, so
 * nothing essential is carried by the motion alone. It still responds to
 * `:focus-visible` on the trigger, which costs nothing and rewards keyboard
 * users who are on the link.
 *
 * Works either as its own trigger (`.t-learn` on this element) or nested
 * inside a parent marked `.group`, which is how it picks up hover from a
 * whole card or button.
 */
export function LearnMoreChevron({
    size = 16,
    className,
}: {
    size?: number
    className?: string
}) {
    return (
        <span className={cn('t-learn-chevron', className)} aria-hidden>
            <svg width={size} height={size} viewBox="0 0 16 16" fill="none">
                {/* Both arms share the apex at (10, 8) as their transform
                    origin, so rotating them in opposite directions opens the
                    angle instead of sliding the whole glyph. */}
                <path
                    className="t-learn-arm t-learn-arm-top"
                    d="M6 4L10 8"
                    stroke="currentColor"
                    strokeWidth={1.6}
                    strokeLinecap="round"
                />
                <path
                    className="t-learn-arm t-learn-arm-bot"
                    d="M10 8L6 12"
                    stroke="currentColor"
                    strokeWidth={1.6}
                    strokeLinecap="round"
                />
            </svg>
        </span>
    )
}
