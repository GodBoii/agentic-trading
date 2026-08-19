import AgentMarkdown from '@/components/agent-markdown'
import { count, humanizeKey } from '@/lib/format'
import { CodeBlock, Disclosure } from './disclosure'

/**
 * Model and tool accounting for one agent run.
 *
 * When the backend captures nothing, this renders nothing. The previous version
 * emitted three placeholder cards reading "Not captured in this run" — filling
 * a third of the workspace with the information that there is no information.
 */
/**
 * Billing is not part of a trading audit trail.
 *
 * Agno writes a `cost` figure into every run's `metrics`, so it arrived in this
 * panel by default and put the model provider's invoice next to the decision the
 * agent made. Filtered on a key match rather than one hardcoded name, because
 * the same block also carries `total_cost` depending on the provider.
 */
function isCostKey(key: string) {
    return /(^|_)cost(_|$)/i.test(key)
}

function readRunMetadata(metadata?: Record<string, unknown> | null) {
    const usage = pickRecord(metadata?.token_usage) || pickRecord(metadata?.metrics)
    const toolSummary = pickRecord(metadata?.tool_summary)
    return {
        usageEntries: scalarEntries(usage).filter(([key]) => !isCostKey(key)),
        // `largest_result` is a payload dump, not a metric; it belongs in raw data.
        summaryEntries: scalarEntries(toolSummary).filter(
            ([key]) => key !== 'largest_result' && !isCostKey(key),
        ),
        toolCalls: Array.isArray(metadata?.tool_calls) ? metadata.tool_calls : [],
        reasoning: readReasoning(metadata),
    }
}

/** Lets callers skip the surrounding panel entirely when there is nothing to show. */
export function hasRunMetadata(metadata?: Record<string, unknown> | null) {
    const { usageEntries, summaryEntries, toolCalls, reasoning } = readRunMetadata(metadata)
    return Boolean(usageEntries.length || summaryEntries.length || toolCalls.length || reasoning)
}

export function RunMetadata({ metadata }: { metadata?: Record<string, unknown> | null }) {
    const { usageEntries, summaryEntries, toolCalls, reasoning } = readRunMetadata(metadata)

    if (!usageEntries.length && !summaryEntries.length && !toolCalls.length && !reasoning) return null

    return (
        <div className="space-y-3">
            {summaryEntries.length > 0 && (
                <MetricRow label="Tool activity" entries={summaryEntries} />
            )}
            {usageEntries.length > 0 && <MetricRow label="Model usage" entries={usageEntries} />}

            {toolCalls.length > 0 && (
                <Disclosure label="Raw tool calls" hint={`${toolCalls.length}`}>
                    <CodeBlock maxHeight={240}>{JSON.stringify(toolCalls, null, 2)}</CodeBlock>
                </Disclosure>
            )}
            {reasoning && (
                <Disclosure label="Reasoning trace">
                    <div className="max-h-80 overflow-auto">
                        <AgentMarkdown>{reasoning}</AgentMarkdown>
                    </div>
                </Disclosure>
            )}
        </div>
    )
}

function MetricRow({ label, entries }: { label: string; entries: [string, unknown][] }) {
    return (
        <div>
            <p className="dash-label mb-2">{label}</p>
            <dl className="cell-grid grid-cols-2 sm:grid-cols-4">
                {entries.map(([key, value]) => (
                    <div key={key} className="px-3.5 py-2.5">
                        <dt className="truncate font-mono text-[9px] uppercase tracking-[0.1em] text-ink-tertiary" title={humanizeKey(key)}>
                            {humanizeKey(key)}
                        </dt>
                        <dd className="nums mt-1 truncate font-mono text-[11.5px] text-ink-primary">
                            {formatMetric(value)}
                        </dd>
                    </div>
                ))}
            </dl>
        </div>
    )
}

function pickRecord(value: unknown): Record<string, unknown> | null {
    return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : null
}

function scalarEntries(source: Record<string, unknown> | null): [string, unknown][] {
    if (!source) return []
    return Object.entries(source).filter(
        ([, value]) => value !== null && value !== undefined && typeof value !== 'object',
    )
}

function formatMetric(value: unknown) {
    if (typeof value === 'number') return Number.isInteger(value) ? count(value) : value.toFixed(2)
    if (typeof value === 'boolean') return value ? 'Yes' : 'No'
    return String(value)
}

function readReasoning(metadata?: Record<string, unknown> | null) {
    const raw = metadata?.reasoning_content || metadata?.reasoning_steps || metadata?.reasoning_messages
    if (!raw) return ''
    return typeof raw === 'string' ? raw : JSON.stringify(raw, null, 2)
}
