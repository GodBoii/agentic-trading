import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

/**
 * EmptyState — says what is missing and what to do about it.
 *
 * `detail` should explain the cause, not restate the title, and `action`
 * should exist wherever the user can actually resolve the emptiness.
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
            <div className="max-w-sm">
                <span aria-hidden className="mx-auto mb-4 block h-7 w-7 rounded-full border border-dashed border-line-strong" />
                <p className="text-[13px] font-medium text-ink-primary">{title}</p>
                <p className="mt-1.5 text-[11px] leading-relaxed text-ink-tertiary">{detail}</p>
                {action && <div className="mt-5 flex justify-center">{action}</div>}
            </div>
        </div>
    )
}
