import AgentMarkdown from '@/components/agent-markdown'
import { PriceLadder } from '@/components/charts/price-ladder'
import { Badge, type Tone } from '@/components/ui/badge'
import { Meter } from '@/components/ui/meter'
import { cn } from '@/lib/cn'
import { count, money, percent, price } from '@/lib/format'
import { interpretDecision, type InterpretedDecision } from './decision'

const INTENT_TONE: Record<InterpretedDecision['intent'], Tone> = {
    buy: 'positive',
    sell: 'negative',
    hold: 'neutral',
    none: 'warning',
    unknown: 'accent',
}

/**
 * Renders an agent decision as a hierarchy: verdict, trade plan, supporting
 * fields, then rationale. See `decision.ts` for why the payload is interpreted
 * rather than enumerated.
 */
export function DecisionPanel({
    decision,
    className,
}: {
    decision?: Record<string, unknown> | null
    className?: string
}) {
    const parsed = interpretDecision(decision)
    if (parsed.isEmpty) return null

    const { plan } = parsed
    const hasPlan = plan.entry !== undefined && (plan.stop !== undefined || plan.target !== undefined)

    return (
        <div className={cn('space-y-4', className)}>
            {(parsed.action || parsed.confidence !== undefined) && (
                <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
                    {parsed.action && (
                        <Badge tone={INTENT_TONE[parsed.intent]} size="lg">
                            {parsed.action}
                        </Badge>
                    )}
                    {parsed.symbol && (
                        <span className="text-[14px] font-medium tracking-[-0.02em] text-ink-primary">
                            {parsed.symbol}
                        </span>
                    )}
                    {parsed.quantity !== undefined && (
                        <span className="nums font-mono text-[11px] text-ink-secondary">
                            {count(parsed.quantity)} qty
                        </span>
                    )}
                    {parsed.capital !== undefined && (
                        <span className="nums font-mono text-[11px] text-ink-secondary">
                            {money(parsed.capital)}
                        </span>
                    )}
                    {parsed.confidence !== undefined && (
                        <span className="ml-auto flex min-w-[132px] items-center gap-2.5">
                            <span className="dash-label">Confidence</span>
                            <Meter
                                className="flex-1"
                                value={parsed.confidence}
                                tone={parsed.confidence >= 66 ? 'positive' : parsed.confidence >= 33 ? 'warning' : 'negative'}
                                label="Agent confidence"
                            />
                            <span className="nums font-mono text-[11px] text-ink-primary">
                                {percent(parsed.confidence, 0)}
                            </span>
                        </span>
                    )}
                </div>
            )}

            {hasPlan && (
                <div className="rounded-xl border border-line bg-panel-inset p-4">
                    <div className="mb-1 flex items-center justify-between gap-3">
                        <p className="dash-label">
                            Trade plan{plan.direction ? ` · ${plan.direction}` : ''}
                        </p>
                        {plan.riskReward !== undefined && (
                            <p className="nums font-mono text-[11px] text-ink-secondary">
                                {plan.riskReward.toFixed(2)}:1 reward to risk
                            </p>
                        )}
                    </div>
                    <PriceLadder plan={plan} className="mt-4" />
                    {(plan.risk !== undefined || plan.reward !== undefined) && (
                        <dl className="mt-4 flex flex-wrap gap-x-6 gap-y-1.5 border-t border-line pt-3 text-[10px] text-ink-tertiary">
                            {plan.risk !== undefined && (
                                <div className="flex gap-1.5">
                                    <dt>Risk per unit</dt>
                                    <dd className="nums font-mono text-negative">{price(plan.risk)}</dd>
                                </div>
                            )}
                            {plan.reward !== undefined && (
                                <div className="flex gap-1.5">
                                    <dt>Reward per unit</dt>
                                    <dd className="nums font-mono text-positive">{price(plan.reward)}</dd>
                                </div>
                            )}
                            {plan.risk !== undefined && parsed.quantity !== undefined && (
                                <div className="flex gap-1.5">
                                    <dt>Risk on {count(parsed.quantity)}</dt>
                                    <dd className="nums font-mono text-ink-secondary">
                                        {money(plan.risk * parsed.quantity)}
                                    </dd>
                                </div>
                            )}
                        </dl>
                    )}
                </div>
            )}

            {parsed.fields.length > 0 && (
                <dl className="cell-grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4">
                    {parsed.fields.map((field) => (
                        <div key={field.key} className="px-3.5 py-3">
                            <dt className="dash-label truncate" title={field.label}>
                                {field.label}
                            </dt>
                            <dd className="nums mt-1.5 break-words font-mono text-[11.5px] text-ink-primary">
                                {field.value}
                            </dd>
                        </div>
                    ))}
                </dl>
            )}

            {parsed.prose.map((entry) => (
                <div key={entry.key} className="rounded-xl border border-line bg-panel-inset p-4">
                    <p className="dash-label mb-2.5">{entry.label}</p>
                    <AgentMarkdown>{entry.text}</AgentMarkdown>
                </div>
            ))}
        </div>
    )
}
