import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

/**
 * Panel — the framed reading surface every data view sits in.
 *
 * Structural styling lives in `.panel*` (globals.css) so nested tables and
 * cell grids clip against the same radius.
 */
export function Panel({
    children,
    className,
    as: Tag = 'section',
    ...rest
}: {
    children: ReactNode
    className?: string
    as?: 'section' | 'div' | 'article'
    'aria-labelledby'?: string
    'aria-label'?: string
}) {
    return (
        <Tag className={cn('panel', className)} {...rest}>
            {children}
        </Tag>
    )
}

/**
 * PanelHeader — eyebrow label, title, optional description, right-hand actions.
 * `id` is wired to the title so the panel can be `aria-labelledby` it.
 */
export function PanelHeader({
    label,
    title,
    description,
    actions,
    titleId,
    className,
}: {
    label?: string
    title: ReactNode
    description?: string
    actions?: ReactNode
    titleId?: string
    className?: string
}) {
    return (
        <header className={cn('panel-header', className)}>
            <div className="min-w-0">
                {label && <p className="dash-label mb-1">{label}</p>}
                <h3 id={titleId} className="truncate text-[13px] font-medium tracking-[-0.02em] text-ink-primary">
                    {title}
                </h3>
                {description && (
                    <p className="mt-1 max-w-prose text-[11px] leading-relaxed text-ink-tertiary">{description}</p>
                )}
            </div>
            {actions && <div className="flex flex-shrink-0 items-center gap-2">{actions}</div>}
        </header>
    )
}

export function PanelBody({ children, className }: { children: ReactNode; className?: string }) {
    return <div className={cn('panel-body', className)}>{children}</div>
}

export function PanelFooter({ children, className }: { children: ReactNode; className?: string }) {
    return <div className={cn('panel-footer', className)}>{children}</div>
}

/**
 * Hairline cell grid. Column counts come from the caller so callers keep
 * control of responsive behaviour; `flush` drops the frame when the grid is
 * already inside a Panel.
 */
export function CellGrid({
    children,
    className,
    flush,
}: {
    children: ReactNode
    className?: string
    flush?: boolean
}) {
    return <div className={cn('cell-grid', flush && 'cell-grid-flush', className)}>{children}</div>
}
