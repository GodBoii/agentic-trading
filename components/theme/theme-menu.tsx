'use client'

import { useEffect, useRef } from 'react'
import { Dropdown, useDropdown } from '@/components/motion/dropdown'
import { Contrast, Moon, Sun } from '@/components/ui/icons'
import { cn } from '@/lib/cn'
import { AppearanceControl } from './appearance-control'

const MENU_ID = 'appearance-menu'

/**
 * Appearance control for the public pages, where there is no account menu to put
 * the setting in.
 *
 * A menu rather than a cycling button, and rather than a sun/moon switch. The
 * switch cannot express "follow the system", which is the most useful of the
 * three states. The cycle can, but it hides what pressing it will do, and its
 * glyph has to change with the current choice — which is a hydration problem, not
 * just a usability one: the server has no way to know the stored preference, so
 * it renders one glyph and the client immediately renders another.
 *
 * The trigger sidesteps that entirely. All three glyphs are in the markup and CSS
 * picks the live one off `html[data-theme-choice]`, which the pre-hydration script
 * has already set. Identical HTML on both sides, correct icon in the first frame,
 * no effect involved. The accessible name stays static for the same reason: a
 * label that described the current state would be a prop mismatch.
 *
 * The setting itself is the same three-option group the account menu uses, so
 * there is one appearance control in the product rendered in two places rather
 * than two controls to keep in step.
 */
export function ThemeMenu({ className }: { className?: string }) {
    const { open, toggle, anchor } = useDropdown<HTMLDivElement>()
    const trigger = useRef<HTMLButtonElement | null>(null)
    const surface = useRef<HTMLDivElement | null>(null)
    const opened = useRef(false)

    useEffect(() => {
        if (open) {
            opened.current = true
            const frame = window.requestAnimationFrame(() => surface.current?.focus())
            return () => window.cancelAnimationFrame(frame)
        }
        if (opened.current) trigger.current?.focus()
    }, [open])

    return (
        <div ref={anchor} className={cn('relative', className)}>
            <button
                ref={trigger}
                type="button"
                onClick={toggle}
                aria-haspopup="dialog"
                aria-expanded={open}
                aria-controls={open ? MENU_ID : undefined}
                aria-label="Appearance"
                className={cn(
                    't-press t-tap grid h-8 w-8 place-items-center rounded-lg border text-ink-secondary',
                    'transition-[color,background-color,border-color] duration-fast ease-smooth',
                    open
                        ? 'border-line-strong bg-surface-strong text-ink-primary'
                        : 'border-line hover:border-line-strong hover:bg-surface-hover hover:text-ink-primary',
                )}
            >
                {/* One of these three is displayed, chosen by CSS from the
                    attribute the bootstrap script wrote. `system` also covers the
                    no-JavaScript case, where no attribute exists at all. */}
                <span className="theme-glyph" data-for="system" aria-hidden>
                    <Contrast size={15} />
                </span>
                <span className="theme-glyph" data-for="light" aria-hidden>
                    <Sun size={15} />
                </span>
                <span className="theme-glyph" data-for="dark" aria-hidden>
                    <Moon size={15} />
                </span>
            </button>

            <Dropdown
                open={open}
                origin="top-right"
                role="dialog"
                ariaLabel="Appearance"
                id={MENU_ID}
                className="pop-surface absolute right-0 top-[calc(100%+8px)] z-[var(--z-overlay)] w-[228px] p-2"
            >
                <div ref={surface} tabIndex={-1} className="outline-none">
                    <p id="appearance-menu-label" className="mb-2 px-1.5 text-[9px] uppercase tracking-[0.14em] text-ink-tertiary">
                        Appearance
                    </p>
                    {/*
                     * Deliberately stays open after a choice. Appearance is the
                     * one setting people try more than once — you pick light,
                     * look at the page, and go back — and dismissing the panel on
                     * every selection makes comparing the two a four-click job.
                     * Escape and an outside click both close it.
                     */}
                    <AppearanceControl labelledBy="appearance-menu-label" />
                </div>
            </Dropdown>
        </div>
    )
}
