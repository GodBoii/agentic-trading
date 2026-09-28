'use client'

import { useCallback, useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Panel } from '@/components/ui/panel'
import { Skeleton } from '@/components/ui/skeleton'
import { Toggle } from '@/components/motion/toggle'

/** Fired after either control on the Agent page writes the trading config. */
export const TRADING_CONFIG_EVENT = 'trading-config-change'

interface AgentConfig {
    enabled?: boolean
    configured?: boolean
    trade_mode?: 'auto' | 'manual'
    trade_amount?: number | null
}

type Load =
    | { kind: 'loading' }
    | { kind: 'error'; message: string }
    | { kind: 'ready'; config: AgentConfig }

/** `confirm` is the one extra step before turning the agent on. */
type Action = 'idle' | 'confirm' | 'saving'

/**
 * The agent's on/off switch.
 *
 * On and off are stored on the same trading configuration the capital
 * setting writes (Convex `tradingConfigurations.enabled`), which is what the
 * backend reads to decide whose accounts it runs for. The switch goes through
 * `/api/ai-trading/toggle`, and the backend queues a scan when it is turned on.
 *
 * Turning off is immediate, because stopping is the safe direction. Turning
 * on asks once, because it starts a scan that can place real orders.
 */
export function AgentSwitch() {
    const [load, setLoad] = useState<Load>({ kind: 'loading' })
    const [action, setAction] = useState<Action>('idle')
    const [error, setError] = useState<string | null>(null)

    const read = useCallback(async () => {
        try {
            const response = await fetch('/api/ai-trading/config', { cache: 'no-store' })
            const payload = await response.json().catch(() => null)
            if (!response.ok) throw new Error(payload?.error || 'Could not read the agent setting.')
            setLoad({ kind: 'ready', config: payload })
        } catch (readError) {
            setLoad({
                kind: 'error',
                message: readError instanceof Error ? readError.message : 'Could not read the agent setting.',
            })
        }
    }, [])

    useEffect(() => {
        void read()
    }, [read])

    // Saving capital for the first time turns the agent on, so re-read then.
    useEffect(() => {
        const onChange = (event: Event) => {
            if ((event as CustomEvent<{ source?: string }>).detail?.source === 'switch') return
            void read()
        }
        window.addEventListener(TRADING_CONFIG_EVENT, onChange)
        return () => window.removeEventListener(TRADING_CONFIG_EVENT, onChange)
    }, [read])

    const write = async (enabled: boolean, config: AgentConfig) => {
        setAction('saving')
        setError(null)
        try {
            const response = await fetch('/api/ai-trading/toggle', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                // The start request carries the saved sizing, so a fixed-amount
                // account is not started as if it were on auto.
                body: JSON.stringify({
                    enabled,
                    trade_mode: config.trade_mode === 'manual' ? 'manual' : 'auto',
                    trade_amount: config.trade_mode === 'manual' ? config.trade_amount ?? undefined : undefined,
                }),
            })
            const payload = await response.json().catch(() => null)
            if (!response.ok) throw new Error(payload?.error || 'The agent could not be switched.')
            setLoad({ kind: 'ready', config: { ...config, enabled: Boolean(payload?.enabled) } })
            window.dispatchEvent(new CustomEvent(TRADING_CONFIG_EVENT, { detail: { source: 'switch' } }))
            setAction('idle')
        } catch (writeError) {
            setError(writeError instanceof Error ? writeError.message : 'The agent could not be switched.')
            setAction('idle')
        }
    }

    if (load.kind === 'loading') {
        return (
            <Panel>
                <div className="flex items-center justify-between gap-4 px-4 py-4 sm:px-5">
                    <div className="min-w-0 flex-1">
                        <Skeleton className="h-3.5 w-28" />
                        <Skeleton className="mt-2 h-3 w-56 max-w-full" delay={40} />
                    </div>
                    <Skeleton className="h-5 w-9 rounded-full" delay={80} />
                </div>
            </Panel>
        )
    }

    if (load.kind === 'error') {
        return (
            <Panel>
                <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-4 sm:px-5">
                    <p className="text-sm text-ink-secondary">{load.message}</p>
                    <Button size="md" variant="subtle" onClick={() => void read()}>
                        Try again
                    </Button>
                </div>
            </Panel>
        )
    }

    const { config } = load
    const on = Boolean(config.enabled)
    const configured = Boolean(config.configured)
    const busy = action === 'saving'

    const description = !configured
        ? 'Save capital per trade below before turning the agent on.'
        : on
          ? 'Scanning for your account and placing orders inside your capital limit.'
          : 'Off. No new runs start for your account.'

    return (
        <Panel aria-labelledby="agent-switch-title">
            <div className="flex items-center gap-4 px-4 py-4 sm:px-5">
                <span
                    aria-hidden
                    className={on ? 'dash-dot dash-dot-positive dash-dot-pulse' : 'dash-dot dash-dot-muted'}
                />
                <div className="min-w-0 flex-1">
                    <p id="agent-switch-title" className="text-[15px] font-medium tracking-[-0.015em] text-ink-primary">
                        Agent {on ? 'on' : 'off'}
                    </p>
                    <p className="mt-0.5 text-[13px] leading-relaxed text-ink-secondary">{description}</p>
                </div>
                <Toggle
                    checked={on}
                    label="Agent trading"
                    disabled={busy || !configured || action === 'confirm'}
                    className="t-tap"
                    onChange={(next) => {
                        if (next) setAction('confirm')
                        else void write(false, config)
                    }}
                />
            </div>

            {action === 'confirm' && (
                <div className="flex flex-wrap items-center gap-3 border-t border-line px-4 py-3.5 sm:px-5" role="group" aria-label="Confirm turning the agent on">
                    <p className="min-w-0 flex-1 basis-60 text-[13px] text-ink-secondary">
                        This starts a scan now. Agents can place orders on Dhan within your capital limit.
                    </p>
                    <div className="flex gap-2">
                        <Button size="md" variant="subtle" onClick={() => setAction('idle')}>
                            Cancel
                        </Button>
                        <Button size="md" variant="solid" onClick={() => void write(true, config)}>
                            Turn on
                        </Button>
                    </div>
                </div>
            )}

            {busy && (
                <p className="border-t border-line px-4 py-3 text-[13px] text-ink-tertiary sm:px-5" role="status">
                    {on ? 'Turning off…' : 'Turning on…'}
                </p>
            )}
            {error && (
                <p role="alert" className="border-t border-line px-4 py-3 text-[13px] text-negative sm:px-5">
                    {error}
                </p>
            )}
        </Panel>
    )
}
