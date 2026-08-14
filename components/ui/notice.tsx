import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'
import { Alert } from './icons'

export type NoticeTone = 'danger' | 'warning' | 'neutral'

const TONE: Record<NoticeTone, { wrap: string; icon: string }> = {
    danger: { wrap: 'border-danger/25 bg-danger/[0.05] text-danger', icon: 'text-danger' },
    warning: { wrap: 'border-warning/25 bg-warning/[0.05] text-warning', icon: 'text-warning' },
    neutral: { wrap: 'border-line bg-white/[0.02] text-ink-secondary', icon: 'text-ink-tertiary' },
}

/**
 * Inline notice for recoverable conditions — a partial data failure, an expired
 * broker token, a degraded stream. Carries its own remedy via `action` so the
 * message is never a dead end.
 */
export function Notice({
    tone = 'neutral',
    children,
    action,
    className,
}: {
    tone?: NoticeTone
    children: ReactNode
    action?: ReactNode
    className?: string
}) {
    const styles = TONE[tone]
    return (
        <div
            role={tone === 'danger' ? 'alert' : 'status'}
            className={cn(
                'flex flex-col gap-2.5 rounded-xl border px-3.5 py-3 sm:flex-row sm:items-center sm:justify-between',
                styles.wrap,
                className,
            )}
        >
            <div className="flex min-w-0 items-start gap-2.5">
                <Alert className={cn('mt-px flex-shrink-0', styles.icon)} size={14} />
                <p className="text-[11.5px] leading-relaxed">{children}</p>
            </div>
            {action && <div className="flex flex-shrink-0 items-center gap-2 sm:ml-3">{action}</div>}
        </div>
    )
}
