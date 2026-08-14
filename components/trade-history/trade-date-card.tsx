import { TradeRunCard } from './trade-run-card'
import type { TradeDateGroup } from './types'
import { formatSessionDate, pluralize, sessionTimestamp } from './utils'

export function TradeDateCard({
    group,
    open,
    openingSessionId,
    onToggle,
    onOpenSession,
    onPrefetchSession,
}: {
    group: TradeDateGroup
    open: boolean
    openingSessionId: string | null
    onToggle: () => void
    onOpenSession: (sessionId: string) => void
    onPrefetchSession: (sessionId: string) => void
}) {
    const date = formatSessionDate(sessionTimestamp(group.sessions[0]))
    const panelId = `trade-date-${group.key}`

    return (
        <article
            className={`trade-date-card overflow-hidden rounded-[26px] border bg-[#09090c]/90 shadow-[0_24px_80px_-56px_rgba(0,229,255,0.35)] ${open ? 'border-accent/25' : 'border-white/[0.085]'}`}
        >
            <button
                type="button"
                aria-expanded={open}
                aria-controls={panelId}
                onClick={onToggle}
                className="trade-date-trigger group flex min-h-[132px] w-full items-center justify-between gap-5 bg-white/[0.018] px-5 py-6 text-left sm:px-7"
            >
                <div>
                    <h3 className="font-grotesk text-[26px] font-medium tracking-[-0.04em] text-white sm:text-[32px]">{date.day}</h3>
                    <p className="mt-2 font-mono text-[9px] uppercase tracking-[0.16em] text-ink-tertiary">{date.date}</p>
                </div>
                <div className="flex items-center gap-4 sm:gap-7">
                    <p className="font-mono text-[9px] uppercase tracking-[0.14em] text-ink-tertiary">{pluralize(group.sessions.length, 'run')}</p>
                    <span className="trade-date-toggle grid h-10 w-10 place-items-center rounded-full border border-white/10 text-lg text-white/70 group-hover:border-accent/30 group-hover:text-accent" aria-hidden>
                        <span className="trade-date-toggle-icon">+</span>
                    </span>
                </div>
            </button>

            <div id={panelId} className="trade-date-panel" data-open={open} aria-hidden={!open}>
                <div className="trade-date-panel-inner overflow-hidden">
                    <div className="grid grid-flow-dense grid-cols-1 border-t border-white/[0.07] md:grid-cols-2 xl:grid-cols-3">
                        {group.sessions.map((session) => (
                            <TradeRunCard
                                key={session.session_id}
                                session={session}
                                opening={openingSessionId === session.session_id}
                                disabled={Boolean(openingSessionId)}
                                onOpen={() => onOpenSession(session.session_id)}
                                onPrefetch={() => onPrefetchSession(session.session_id)}
                            />
                        ))}
                    </div>
                </div>
            </div>
        </article>
    )
}
