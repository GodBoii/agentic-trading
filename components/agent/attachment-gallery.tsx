'use client'

import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Document, External } from '@/components/ui/icons'
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
                        <p className="text-[10px] text-ink-tertiary">{count(images.length)} rendered</p>
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
                                        className="group flex items-center gap-3 px-3.5 py-3 transition-colors duration-[250ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:bg-white/[0.025]"
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
 */
function ChartTile({ image }: { image: AgentImageCard }) {
    const src = attachmentImageUrl(image)
    const label = image.title || image.timeframe || image.filename || 'Chart'
    const [loaded, setLoaded] = useState(false)
    const [failed, setFailed] = useState(false)

    const meta =
        [image.date, image.day_type, image.candles ? `${image.candles} candles` : null].filter(Boolean).join(' · ') ||
        image.filename

    return (
        <a
            href={src || undefined}
            target="_blank"
            rel="noreferrer"
            className="t-lift group block overflow-hidden rounded-xl border border-line bg-panel-inset hover:border-line-strong"
        >
            {/* The aspect ratio is fixed before the image arrives, so a grid of
                charts does not reflow as each one lands. */}
            <div className="relative aspect-[4/3] overflow-hidden bg-black/40">
                {src && !failed ? (
                    <>
                        {/* Pulsing placeholder, cross-faded out as the chart
                            cross-blurs in — both on the same 400ms reveal
                            clock, so the swap reads as one motion. */}
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
                            alt={`${label}${image.date ? ` on ${image.date}` : ''}`}
                            loading="lazy"
                            onLoad={() => setLoaded(true)}
                            onError={() => setFailed(true)}
                            className={cn(
                                'h-full w-full object-cover transition-[opacity,filter] duration-[400ms] ease-in-out',
                                loaded ? 'opacity-100 blur-0' : 'opacity-0 blur-[2px]',
                            )}
                        />
                    </>
                ) : (
                    <div className="grid h-full place-items-center font-mono text-[10px] text-ink-tertiary">
                        Chart unavailable
                    </div>
                )}
            </div>
            <div className="flex items-center justify-between gap-2 px-3 py-2.5">
                <div className="min-w-0">
                    <p className="truncate text-[11.5px] text-ink-primary">{label}</p>
                    <p className="truncate font-mono text-[9px] text-ink-tertiary">{meta}</p>
                </div>
                {image.timeframe && (
                    <Badge size="sm" tone="neutral" className="flex-shrink-0">
                        {image.timeframe}
                    </Badge>
                )}
            </div>
        </a>
    )
}
