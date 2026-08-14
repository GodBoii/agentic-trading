import type { TradeSessionSummary } from './types'
import { formatSessionTime, sessionTimestamp, statusColor } from './utils'

export function TradeRunCard({
    session,
    opening,
    disabled,
    onOpen,
    onPrefetch,
}: {
    session: TradeSessionSummary
    opening: boolean
    disabled: boolean
    onOpen: () => void
    onPrefetch: () => void
}) {
    return (
        <button
            type="button"
            onClick={onOpen}
            onPointerDown={onPrefetch}
            onFocus={onPrefetch}
            disabled={disabled}
            aria-busy={opening}
            className="archive-run group relative min-h-[172px] overflow-hidden border-b border-white/[0.07] p-5 text-left disabled:cursor-wait md:border-r xl:min-h-[184px]"
        >
            <span className="archive-run-accent pointer-events-none absolute inset-y-0 left-0 w-[2px] origin-bottom scale-y-0 bg-accent group-hover:scale-y-100 group-focus-visible:scale-y-100" />
            <div className="flex items-start justify-between gap-4">
                <div className="flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.14em] text-ink-tertiary">
                    <span>{formatSessionTime(sessionTimestamp(session))}</span>
                    <span className="text-white/15">/</span>
                    <span>{session.agent_count || 0} agents</span>
                </div>
                <span className={`mt-0.5 h-1.5 w-1.5 flex-shrink-0 rounded-full ${statusColor(session.status)}`} />
            </div>
            <h4 className="archive-run-title mt-8 line-clamp-2 max-w-[28rem] text-[18px] font-medium leading-snug tracking-[-0.025em] text-white">
                {session.title}
            </h4>
            <div className="mt-6 flex items-center justify-between border-t border-white/[0.07] pt-4">
                <span className="font-mono text-[9px] uppercase tracking-[0.13em] text-ink-tertiary">
                    {session.loaded_from_cloud ? 'Cloud archive' : 'Saved archive'}
                </span>
                <span className="inline-flex items-center gap-2 text-[11px] text-accent">
                    <span className={opening ? 'archive-loading-label' : ''}>{opening ? 'Opening' : 'View run'}</span>
                    <span aria-hidden className={opening ? 'archive-spinner' : 'archive-arrow'}>{opening ? '' : '→'}</span>
                </span>
            </div>
        </button>
    )
}
