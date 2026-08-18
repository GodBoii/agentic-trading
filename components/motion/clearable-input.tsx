'use client'

import { useCallback, useEffect, useRef, useState, type InputHTMLAttributes } from 'react'
import { cn } from '@/lib/cn'
import { motionEase, motionMs, motionNum, prefersReducedMotion } from './tokens'

/**
 * Samples a `cubic-bezier(x1,y1,x2,y2)` curve so the JS-driven phases of the
 * clear match the CSS easing used everywhere else. Newton-Raphson on the x
 * polynomial, which converges in a handful of iterations for the shapes in
 * the token set.
 */
function bezier(spec: string): (t: number) => number {
    const match = spec.match(/cubic-bezier\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)/)
    if (!match) return (t) => t
    const [x1, y1, x2, y2] = match.slice(1).map(Number)
    const cx = 3 * x1
    const bx = 3 * (x2 - x1) - cx
    const ax = 1 - cx - bx
    const cy = 3 * y1
    const by = 3 * (y2 - y1) - cy
    const ay = 1 - cy - by

    return (t: number) => {
        if (t <= 0) return 0
        if (t >= 1) return 1
        let s = t
        for (let i = 0; i < 8; i += 1) {
            const dx = ((ax * s + bx) * s + cx) * s - t
            const d = (3 * ax * s + 2 * bx) * s + cx
            if (Math.abs(dx) < 1e-6 || d === 0) break
            s -= dx / d
        }
        return ((ay * s + by) * s + cy) * s
    }
}

/**
 * Recipe 13 — input clear with dissolve.
 *
 * Clearing the field flies the typed value downward with a blur while a soft
 * streak ignites beneath each word and the placeholder falls in from above.
 *
 * This is the one recipe that genuinely requires per-frame JavaScript. The
 * streak's rise/peak/fall envelope and its per-word radial-gradient stack
 * cannot be expressed as static keyframes: the gradient positions depend on
 * where each word actually sits, which depends on the rendered text metrics.
 * A canvas 2D context is used purely to measure those metrics with the
 * input's own computed font.
 *
 * Structure: a real `<input>` carries the value and all keyboard behaviour; a
 * mirror layer visualises it during the clear (the input's own glyphs are made
 * transparent so the text does not double-render); a fake placeholder handles
 * the incoming empty state; a glow layer receives the gradient stack.
 *
 * On this dark surface the streak lightens rather than darkens — `screen`
 * blending with white gradients. The reference `multiply` blend with black
 * gradients is invisible over a near-black field.
 */
export function ClearableInput({
    value,
    onValueChange,
    placeholder = '',
    className,
    inputClassName,
    clearLabel = 'Clear',
    ...rest
}: {
    value: string
    onValueChange: (next: string) => void
    placeholder?: string
    className?: string
    inputClassName?: string
    clearLabel?: string
} & Omit<InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange' | 'placeholder' | 'className'>) {
    const wrap = useRef<HTMLDivElement | null>(null)
    const input = useRef<HTMLInputElement | null>(null)
    const mirror = useRef<HTMLDivElement | null>(null)
    const placeholderEl = useRef<HTMLDivElement | null>(null)
    const glow = useRef<HTMLDivElement | null>(null)
    const measure = useRef<CanvasRenderingContext2D | null>(null)
    const frame = useRef<number | null>(null)
    const [clearing, setClearing] = useState(false)

    useEffect(() => {
        if (typeof document === 'undefined') return
        measure.current = document.createElement('canvas').getContext('2d')
        return () => {
            if (frame.current) cancelAnimationFrame(frame.current)
        }
    }, [])

    /** One radial-gradient layer stack, four blobs per word. */
    const buildGlow = useCallback((text: string) => {
        const context = measure.current
        const field = input.current
        const host = wrap.current
        if (!context || !field || !host) return ''

        const styles = getComputedStyle(field)
        context.font = styles.font || `${styles.fontSize} ${styles.fontFamily}`
        const width = host.clientWidth || 280
        const padLeft = parseFloat(styles.paddingLeft) || 12
        const spread = motionNum('--glow-spread', 1.5)

        const layers: string[] = []
        let x = 0
        // Split on whitespace but keep the separators, so the running x offset
        // stays in step with the real glyph positions.
        text.split(/(\s+)/).forEach((segment) => {
            const segmentWidth = context.measureText(segment).width
            if (segment.trim()) {
                const centre = padLeft + x + segmentWidth / 2
                const halfWidth = Math.max(segmentWidth * 0.45, 8) * spread
                const blobs: [number, number, number, number][] = [
                    [0, 0.8, 7, 0.3],
                    [halfWidth * 0.45, 0.55, 8, 0.24],
                    [-halfWidth * 0.4, 0.65, 6, 0.22],
                    [halfWidth * 0.15, 0.9, 5, 0.18],
                ]
                blobs.forEach(([dx, widthMultiplier, height, alpha]) => {
                    const left = (((centre + dx) / width) * 100).toFixed(2)
                    layers.push(
                        `radial-gradient(ellipse ${Math.max(halfWidth * widthMultiplier, 2).toFixed(1)}px ${height}px at ${left}% 100%, rgba(255,255,255,${alpha}), transparent)`,
                    )
                })
            }
            x += segmentWidth
        })
        return layers.join(', ')
    }, [])

    const clear = useCallback(() => {
        if (clearing || !value) return

        // Reduced motion: clear instantly. Running the envelope and then
        // hiding the result would just add a 1s delay to a destructive action.
        if (prefersReducedMotion()) {
            onValueChange('')
            input.current?.focus({ preventScroll: true })
            return
        }

        const mirrorEl = mirror.current
        const holder = placeholderEl.current
        const glowEl = glow.current
        if (!mirrorEl || !holder || !glowEl) {
            onValueChange('')
            return
        }

        const keepFocus = document.activeElement === input.current
        const text = value.replace(/ /g, '\u00a0')
        mirrorEl.textContent = text

        const total = motionMs('--clear-dur', 1000)
        const outDur = motionMs('--clear-out-dur', 400)
        const inDur = motionMs('--clear-in-dur', 400)
        const outFly = motionNum('--clear-out-fly', 12)
        const inFly = motionNum('--clear-in-fly', 12)
        const blur = motionNum('--clear-blur', 2)
        const delay = motionMs('--glow-delay', 50)
        const peakAt = motionNum('--glow-peak-at', 0.15)
        const peakOpacity = motionNum('--glow-opacity', 0.85)
        const easeOut = bezier(motionEase('--clear-out-ease', ''))
        const easeIn = bezier(motionEase('--clear-in-ease', ''))

        setClearing(true)
        onValueChange('')

        glowEl.style.background = buildGlow(value)
        glowEl.style.opacity = '0'
        holder.style.transform = `translateY(-${inFly}px)`
        holder.style.opacity = '0.9'
        holder.style.filter = `blur(${blur}px)`

        const start = performance.now()
        const tick = (now: number) => {
            const elapsed = now - start

            const out = easeOut(Math.min(1, elapsed / outDur))
            mirrorEl.style.transform = `translateY(${(out * outFly).toFixed(1)}px)`
            mirrorEl.style.opacity = (1 - out).toFixed(3)
            mirrorEl.style.filter = `blur(${(out * blur).toFixed(1)}px)`

            const incoming = easeIn(Math.min(1, elapsed / inDur))
            holder.style.transform = `translateY(${(-inFly + incoming * inFly).toFixed(1)}px)`
            holder.style.opacity = (0.9 + incoming * 0.1).toFixed(3)
            holder.style.filter = `blur(${(blur - incoming * blur).toFixed(1)}px)`

            // Triangular envelope: fast rise to the peak, slow decay after.
            let glowLevel = 0
            if (elapsed > delay) {
                const progress = Math.min(1, (elapsed - delay) / Math.max(1, total - delay))
                glowLevel = progress < peakAt ? progress / peakAt : 1 - (progress - peakAt) / (1 - peakAt)
            }
            glowEl.style.opacity = (glowLevel * peakOpacity).toFixed(3)

            if (elapsed < total) {
                frame.current = requestAnimationFrame(tick)
                return
            }

            // Reset every inline style the envelope wrote, or the next clear
            // starts from wherever this one finished.
            mirrorEl.style.cssText = ''
            holder.style.cssText = ''
            mirrorEl.textContent = ''
            glowEl.style.opacity = '0'
            glowEl.style.background = ''
            setClearing(false)
            if (keepFocus) requestAnimationFrame(() => input.current?.focus({ preventScroll: true }))
        }
        frame.current = requestAnimationFrame(tick)
    }, [buildGlow, clearing, onValueChange, value])

    const hasValue = value.length > 0

    return (
        <div
            ref={wrap}
            className={cn(
                't-clear relative flex items-center rounded-xl border border-line bg-white/[0.03]',
                hasValue && 'has-value',
                clearing && 'is-clearing',
                className,
            )}
        >
            <input
                ref={input}
                value={value}
                onChange={(event) => onValueChange(event.target.value)}
                placeholder={placeholder}
                className={cn(
                    'relative z-[1] h-9 min-w-0 flex-1 border-0 bg-transparent px-3 font-mono text-[12px] text-ink-primary outline-none placeholder:text-ink-tertiary',
                    inputClassName,
                )}
                {...rest}
            />

            {/* Visualises the value during the clear. */}
            <div ref={mirror} className="t-clear-mirror px-3 font-mono text-[12px] text-ink-primary" aria-hidden />
            {/* The incoming empty state, falling in from above. */}
            <div
                ref={placeholderEl}
                className="t-clear-placeholder px-3 font-mono text-[12px] text-ink-tertiary"
                aria-hidden
            >
                {placeholder}
            </div>
            <div ref={glow} className="t-clear-glow" aria-hidden />

            {hasValue && (
                <button
                    type="button"
                    // Suppressing the default on press keeps focus in the
                    // field, so clearing does not also dismiss the keyboard.
                    onPointerDown={(event) => {
                        if (document.activeElement === input.current) event.preventDefault()
                    }}
                    onClick={clear}
                    aria-label={clearLabel}
                    className="t-clear-btn t-press relative z-[4] mr-1.5 grid h-6 w-6 flex-shrink-0 place-items-center rounded-md text-ink-tertiary transition-colors duration-150 hover:bg-white/[0.06] hover:text-ink-primary"
                >
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" aria-hidden>
                        <path d="M6 6l12 12M18 6L6 18" />
                    </svg>
                </button>
            )}
        </div>
    )
}
