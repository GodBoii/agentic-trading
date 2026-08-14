import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'
import { type Direction } from '@/lib/format'

export interface Column<T> {
    key: string
    header: string
    align?: 'left' | 'right' | 'center'
    /** Rendered into the body cell. */
    render: (row: T) => ReactNode
    /** Colours the cell by P&L sign. */
    direction?: (row: T) => Direction
    /** Hides the column below the given breakpoint to keep mobile readable. */
    hideBelow?: 'sm' | 'md' | 'lg'
}

const HIDE_CLASS = {
    sm: 'hidden sm:table-cell',
    md: 'hidden md:table-cell',
    lg: 'hidden lg:table-cell',
} as const

const DIRECTION_TEXT: Record<Direction, string> = {
    positive: 'text-positive',
    negative: 'text-negative',
    neutral: '',
}

/**
 * DataTable — column-driven so alignment is declared once and applied to both
 * the header and the body cell. The previous hand-rolled version repeated
 * `text-right` on every `<th>` and `<td>` independently, which is how columns
 * drift out of alignment.
 *
 * Vertical scrolling lives on `.table-scroll` so the sticky header works;
 * `minWidth` drives horizontal scroll rather than squashing columns.
 */
export function DataTable<T>({
    columns,
    rows,
    rowKey,
    caption,
    minWidth = 760,
    maxHeight,
}: {
    columns: Column<T>[]
    rows: T[]
    rowKey: (row: T, index: number) => string
    /** Accessible description of the table. Visually hidden. */
    caption: string
    minWidth?: number
    maxHeight?: number | string
}) {
    return (
        <div className="table-scroll" style={maxHeight ? { maxHeight } : undefined}>
            <table className="data-table" style={{ minWidth }}>
                <caption className="sr-only">{caption}</caption>
                <thead>
                    <tr>
                        {columns.map((column) => (
                            <th
                                key={column.key}
                                scope="col"
                                data-align={column.align}
                                className={column.hideBelow && HIDE_CLASS[column.hideBelow]}
                            >
                                {column.header}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {rows.map((row, index) => (
                        <tr key={rowKey(row, index)}>
                            {columns.map((column) => (
                                <td
                                    key={column.key}
                                    data-align={column.align}
                                    className={cn(
                                        column.hideBelow && HIDE_CLASS[column.hideBelow],
                                        column.direction && DIRECTION_TEXT[column.direction(row)],
                                    )}
                                >
                                    {column.render(row)}
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    )
}

/**
 * Instrument identity cell: symbol on top, venue/id beneath. Uses the sans
 * face for the symbol so it reads as a name rather than a figure.
 */
export function Instrument({ symbol, meta }: { symbol: string; meta?: string }) {
    return (
        <div className="min-w-0">
            <p className="truncate font-sans text-[12px] font-medium text-ink-primary">{symbol}</p>
            {meta && <p className="mt-0.5 truncate font-mono text-[9px] text-ink-tertiary">{meta}</p>}
        </div>
    )
}
