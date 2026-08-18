'use client'

import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'
import { Reveal } from '@/components/motion/reveal'

/**
 * EmptyState — says what is missing and what to do about it.
 *
 * `detail` should explain the cause, not restate the title, and `action`
 * should exist wherever the user can actually resolve the emptiness.
 *
 * Motion. The copy uses the texts-reveal recipe (recipe 18): title, detail and
 * action rise with a 40ms stagger. An empty state is almost always the result
 * of a fetch that just settled, so it arrives as a replacement for a skeleton —
 * a staggered entrance reads as content landing, whereas a hard cut reads as
 * the screen having failed. Plays on mount rather than on scroll, since an
 * empty state is the only thing in its container.
 *
 * The dashed ring is decorative and deliberately not an icon: a glyph here
 * would have to mean something, and "nothing is here" has no good glyph.
 */
export function EmptyState({
    title,
    detail,
    action,
    minHeight = 320,
    className,
}: {
    title: string
    detail: string
    action?: ReactNode
    minHeight?: number
    className?: string
}) {
    return (
        <div className={cn('grid place-items-center px-6 py-12 text-center', className)} style={{ minHeight }}>
            <Reveal immediate className="max-w-sm">
                <span
                    aria-hidden
                    className="mx-auto mb-4 block h-7 w-7 rounded-full border border-dashed border-line-strong"
                />
                <p className="text-[13px] font-medium text-ink-primary">{title}</p>
                <p className="mt-1.5 text-[11px] leading-relaxed text-ink-tertiary">{detail}</p>
                {action ? <div className="mt-5 flex justify-center">{action}</div> : <></>}
            </Reveal>
        </div>
    )
}
