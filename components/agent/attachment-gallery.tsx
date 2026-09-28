'use client'

import { useId, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Close, Document, External } from '@/components/ui/icons'
import { Modal } from '@/components/motion/modal'
import { cn } from '@/lib/cn'
import { attachmentFileUrl, attachmentImageUrl } from '@/components/ai-trading/utils'
import type { AgentAttachments, AgentImageCard } from '@/components/ai-trading/types'
import { count } from '@/lib/format'

/**
 * Charts and files produced by an agent run.
 *
 * Charts use a grid rather than a horizontal scroll rail: the whole point of a
 * multi-timeframe set is comparison, and a rail hides all but the first two
 * behind a scroll gesture. The timeframe is promoted to a badge because it is
 * the distinguishing attribute between otherwise identical thumbnails.
 *
 * Motion. This is the one surface in the product where the image-generation
 * role from the motion skill genuinely applies: these are backend-rendered
 * matplotlib PNGs of unknown size, fetched after the event that references them
 * has already arrived, so each tile really does materialise. Each one holds a
 * pulsing placeholder at the correct aspect ratio and cross-blurs the chart in
 * on load (recipe 14).
 *
 * That is worth doing here for a concrete reason beyond polish: without a
 * reserved box, a grid of six charts reflows six times as they arrive, and the
 * reader loses their place mid-comparison. The placeholder fixes the geometry
 * and the cross-fade means the arrival is legible rather than a flicker.
 *
 * A shader-driven mosaic would be the wrong call — these are finished renders
 * being loaded, not images being generated in front of the user, so implying
 * generation would misrepresent what is happening.
 */
export function AttachmentGallery({ attachments }: { attachments?: AgentAttachments | null }) {
    const images = attachments?.images || []
    const files = attachments?.files || []
    if (!images.length && !files.length) return null

    return (
        <div className="space-y-5">
            {images.length > 0 && (
                <section>
                    <div className="mb-3 flex items-center justify-between">
                        <p className="dash-label">Charts</p>
                        <p className="text-xs text-ink-tertiary">{count(images.length)} rendered</p>
                    </div>
                    <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                        {images.map((image, index) => (
                            <li key={image.id || image.filename || index}>
                                <ChartTile image={image} />
                            </li>
                        ))}
                    </ul>
                </section>
            )}

            {files.length > 0 && (
                <section>
                    <p className="dash-label mb-3">Artifacts</p>
                    <ul className="cell-grid grid-cols-1 sm:grid-cols-2">
                        {files.map((file, index) => {
                            const href = attachmentFileUrl(file)
                            return (
                                <li key={file.id || file.filename || index}>
                                    <a
                                        href={href || undefined}
                                        target="_blank"
                                        rel="noreferrer"
                                        className="group flex items-center gap-3 px-3.5 py-3 transition-colors duration-fast ease-smooth hover:bg-surface-hover"
                                    >
                                        <Document size={15} className="flex-shrink-0 text-ink-tertiary" />
                                        <span className="min-w-0 flex-1">
                                            <span className="block truncate text-[11.5px] text-ink-primary">
                                                {file.title || file.filename || 'Artifact'}
                                            </span>
                                            <span className="block truncate font-mono text-[9px] text-ink-tertiary">
                                                {file.storage_path || file.path || file.content_type || 'file'}
                                            </span>
                                        </span>
                                        <External
                                            size={13}
                                            className="flex-shrink-0 text-ink-tertiary transition-colors duration-[250ms] group-hover:text-ink-secondary"
                                        />
                                    </a>
                                </li>
                            )
                        })}
                    </ul>
                </section>
            )}
        </div>
    )
}

/**
 * One chart, with its own load state.
 *
 * State is per-tile rather than lifted: charts arrive independently and in any
 * order, so a shared "images loading" flag would hold every tile behind the
 * slowest one.
 *
 * The tile keeps the chart's own aspect ratio once it loads. A fixed 4:3 box
 * with object-cover cut the axes off wide matplotlib renders. Tapping opens
 * the chart in a viewer on this page instead of a raw PNG in a new tab.
 */
function ChartTile({ image }: { image: AgentImageCard }) {
    const src = attachmentImageUrl(image)
    const label = image.title || image.timeframe || image.filename || 'Chart'
    const [loaded, setLoaded] = useState(false)
    const [failed, setFailed] = useState(false)
    const [viewing, setViewing] = useState(false)
    const titleId = useId()

    const meta = [image.date, image.day_type, image.candles ? `${image.candles} candles` : null]
        .filter(Boolean)
        .join(' · ')
    const alt = `${label}${image.date ? ` on ${image.date}` : ''}`

    return (
        <>
            <button
                type="button"
                onClick={() => setViewing(true)}
                disabled={!src || failed}
                aria-label={`View chart: ${alt}`}
                className="group block w-full overflow-hidden rounded-xl border border-line bg-panel-inset text-left transition-colors duration-fast ease-smooth hover:border-line-strong disabled:cursor-default"
            >
                <div className={cn('relative overflow-hidden bg-black/40', !loaded && 'aspect-[16/10]')}>
                    {src && !failed ? (
                        <>
                            <span
                                aria-hidden
                                className={cn(
                                    'archive-skeleton absolute inset-0 transition-opacity duration-[400ms] ease-in-out',
                                    loaded ? 'opacity-0' : 'opacity-100',
                                )}
                            />
                            {/* Backend-rendered matplotlib PNGs of arbitrary size;
                                next/image would add no value over a direct load. */}
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img
                                src={src}
                                alt={alt}
                                loading="lazy"
                                decoding="async"
                                onLoad={() => setLoaded(true)}
                                onError={() => setFailed(true)}
                                className={cn(
                                    'block w-full transition-[opacity,filter] duration-[400ms] ease-in-out',
                                    loaded ? 'h-auto opacity-100 blur-0' : 'absolute inset-0 h-full opacity-0 blur-[2px]',
                                )}
                            />
                        </>
                    ) : (
                        <div className="grid aspect-[16/10] place-items-center text-sm text-ink-tertiary">
                            Chart unavailable
                        </div>
                    )}
                </div>
                <div className="flex items-center justify-between gap-2 px-3 py-2.5">
                    <div className="min-w-0">
                        <p className="truncate text-sm text-ink-primary">{label}</p>
                        {meta && <p className="nums truncate text-xs text-ink-tertiary">{meta}</p>}
                    </div>
                    {image.timeframe && (
                        <Badge size="sm" tone="neutral" className="flex-shrink-0">
                            {image.timeframe}
                        </Badge>
                    )}
                </div>
            </button>

            {src && (
                <Modal open={viewing} onClose={() => setViewing(false)} labelledBy={titleId} size="wide">
                    <div className="flex max-h-[92dvh] flex-col">
                        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
                            <div className="min-w-0">
                                <h2 id={titleId} className="truncate text-[15px] font-medium text-ink-primary">
                                    {label}
                                </h2>
                                {meta && <p className="nums truncate text-xs text-ink-tertiary">{meta}</p>}
                            </div>
                            <div className="flex flex-shrink-0 items-center gap-1">
                                <a
                                    href={src}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="grid h-11 w-11 place-items-center rounded-xl text-ink-secondary hover:bg-surface-hover"
                                    aria-label="Open original image"
                                >
                                    <External size={17} />
                                </a>
                                <button
                                    type="button"
                                    onClick={() => setViewing(false)}
                                    className="grid h-11 w-11 place-items-center rounded-xl text-ink-secondary hover:bg-surface-hover"
                                    aria-label="Close chart"
                                >
                                    <Close size={18} />
                                </button>
                            </div>
                        </header>
                        {/* Scrolls in both directions, so a wide chart can be
                            panned on a phone at full resolution. */}
                        <div className="min-h-0 flex-1 overflow-auto overscroll-contain bg-black/60">
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img src={src} alt={alt} className="mx-auto block h-auto max-w-none sm:max-w-full" />
                        </div>
                    </div>
                </Modal>
            )}
        </>
    )
}
