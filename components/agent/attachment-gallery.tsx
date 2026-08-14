import { Badge } from '@/components/ui/badge'
import { Document, External } from '@/components/ui/icons'
import { attachmentFileUrl, attachmentImageUrl } from '@/components/ai-trading/utils'
import type { AgentAttachments } from '@/components/ai-trading/types'
import { count } from '@/lib/format'

/**
 * Charts and files produced by an agent run.
 *
 * Charts use a grid rather than the previous horizontal scroll rail: the whole
 * point of a multi-timeframe set is comparison, and a rail hides all but the
 * first two behind a scroll gesture. The timeframe is promoted to a badge
 * because it is the distinguishing attribute between otherwise identical
 * thumbnails.
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
                        {images.map((image, index) => {
                            const src = attachmentImageUrl(image)
                            const label = image.title || image.timeframe || image.filename || 'Chart'
                            return (
                                <li key={image.id || image.filename || index}>
                                    <a
                                        href={src || undefined}
                                        target="_blank"
                                        rel="noreferrer"
                                        className="group block overflow-hidden rounded-xl border border-line bg-panel-inset transition-colors hover:border-line-strong"
                                    >
                                        <div className="aspect-[4/3] overflow-hidden bg-black/40">
                                            {src ? (
                                                // Backend-rendered matplotlib PNGs of arbitrary size;
                                                // next/image would add no value over a direct load here.
                                                // eslint-disable-next-line @next/next/no-img-element
                                                <img
                                                    src={src}
                                                    alt={`${label}${image.date ? ` on ${image.date}` : ''}`}
                                                    loading="lazy"
                                                    className="h-full w-full object-cover"
                                                />
                                            ) : (
                                                <div className="grid h-full place-items-center font-mono text-[10px] text-ink-tertiary">
                                                    Chart unavailable
                                                </div>
                                            )}
                                        </div>
                                        <div className="flex items-center justify-between gap-2 px-3 py-2.5">
                                            <div className="min-w-0">
                                                <p className="truncate text-[11.5px] text-ink-primary">{label}</p>
                                                <p className="truncate font-mono text-[9px] text-ink-tertiary">
                                                    {[image.date, image.day_type, image.candles ? `${image.candles} candles` : null]
                                                        .filter(Boolean)
                                                        .join(' · ') || image.filename}
                                                </p>
                                            </div>
                                            {image.timeframe && (
                                                <Badge size="sm" tone="neutral" className="flex-shrink-0">
                                                    {image.timeframe}
                                                </Badge>
                                            )}
                                        </div>
                                    </a>
                                </li>
                            )
                        })}
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
                                        className="flex items-center gap-3 px-3.5 py-3 transition-colors hover:bg-white/[0.025]"
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
                                        <External size={13} className="flex-shrink-0 text-ink-tertiary" />
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
