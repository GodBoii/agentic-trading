'use client'

import { FormEvent, useCallback, useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'

type Connection = {
    connected: boolean
    dhanClientId?: string
    tokenExpiresAt?: string | null
    authStatus?: string
    authError?: string | null
    autoRenew?: boolean
    recoveryConfigured?: boolean
    renewalOwner?: string
    lastCheckedAt?: string | null
    nextRenewalAt?: string | null
    staticIp?: string | null
    ipCheckedAt?: string | null
    redirectUrl?: string
}

function timestamp(value?: string | null) {
    if (!value || !Number.isFinite(Date.parse(value))) return 'Not available yet'
    return new Date(value).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) + ' IST'
}

const reasons: Record<string, string> = {
    user_dhan_invalid_token: 'Dhan rejected the current token. Automatic recovery will retry if configured.',
    user_dhan_static_ip_not_allowed: 'Dhan has not confirmed order access from this server. Check your IP registration.',
    user_dhan_order_access_unavailable: 'The broker order-access check is unavailable.',
    renewal_failed_or_recovery_missing: 'Renewal failed. Check recovery credentials or reconnect Dhan.',
    verify_account_once: 'Connect a valid token once to verify ownership of this account.',
    scanner_auth_unavailable: 'The shared account authentication service needs attention.',
    invalid_or_expired_token: 'The broker token is invalid or expired. Update it or reconnect Dhan.',
}

function CopyValue({ label, value }: { label: string; value?: string | null }) {
    const [message, setMessage] = useState('Copy')
    return <div className="min-w-0">
        <p className="mb-2 text-xs text-ink-secondary">{label}</p>
        <div className="flex min-h-11 items-center gap-3 rounded-xl border border-line bg-surface px-3">
            <code className="min-w-0 flex-1 break-all text-xs text-ink-primary">{value || 'Waiting for backend verification'}</code>
            <button type="button" disabled={!value} aria-label={'Copy ' + label} className="min-h-11 shrink-0 text-xs text-ink-secondary hover:text-ink-primary disabled:opacity-40"
                onClick={async () => { try { await navigator.clipboard.writeText(value || ''); setMessage('Copied') } catch { setMessage('Copy failed') } }}>{message}</button>
        </div>
    </div>
}

export default function DhanConnect() {
    const heading = useRef<HTMLHeadingElement>(null)
    const [connection, setConnection] = useState<Connection | null>(null)
    const [state, setState] = useState<'loading' | 'idle' | 'saving'>('loading')
    const [message, setMessage] = useState('')
    const [error, setError] = useState('')
    const [editing, setEditing] = useState(false)
    const [confirmDisconnect, setConfirmDisconnect] = useState(false)
    const [clientId, setClientId] = useState('')
    const [autoRenew, setAutoRenew] = useState(false)
    const load = useCallback(async (signal?: AbortSignal) => {
        const response = await fetch('/api/dhan/connection', { cache: 'no-store', signal })
        const data: Connection & { error?: string } = await response.json()
        if (!response.ok) throw new Error(data.error || 'Unable to load authentication')
        setConnection(data)
        return data
    }, [])
    useEffect(() => {
        const controller = new AbortController()
        void load(controller.signal).then(data => { setClientId(data.dhanClientId || ''); setAutoRenew(data.connected ? data.autoRenew || false : true); setEditing(!data.connected) })
            .catch(e => { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Unable to load authentication') })
            .finally(() => { if (!controller.signal.aborted) setState('idle') })
        const interval = window.setInterval(() => {
            void load(controller.signal).catch(() => { if (!controller.signal.aborted) setError('Unable to refresh authentication status.') })
        }, 30_000)
        return () => { controller.abort(); window.clearInterval(interval) }
    }, [load])

    const save = async (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault()
        const form = event.currentTarget
        const values = new FormData(form)
        setState('saving'); setError(''); setMessage('')
        try {
            const response = await fetch('/api/dhan/settings', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
                dhanClientId: clientId, apiKey: values.get('apiKey'), apiSecret: values.get('apiSecret'), accessToken: values.get('accessToken'),
                pin: values.get('pin'), totpSecret: values.get('totpSecret'), autoRenew, clearRecovery: values.get('clearRecovery') === 'on',
            }) })
            const data = await response.json()
            if (!response.ok) throw new Error(data.error || 'Unable to save credentials')
            form.reset(); setEditing(false)
            await load()
            setMessage('Saved. The backend will validate the account on its next check.')
            heading.current?.focus()
            window.dispatchEvent(new CustomEvent('dhan-connection-change'))
        } catch (e) { setError(e instanceof Error ? e.message : 'Unable to save credentials') }
        finally { setState('idle') }
    }
    const reconnect = async () => {
        setState('saving'); setError('')
        try {
            const response = await fetch('/api/dhan/auth', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
            const data = await response.json()
            if (!response.ok) throw new Error(data.error || 'Unable to start Dhan login')
            window.location.assign(data.url)
        } catch (e) { setError(e instanceof Error ? e.message : 'Unable to reconnect'); setState('idle') }
    }
    const disconnect = async () => {
        setState('saving'); setError('')
        try {
            const response = await fetch('/api/dhan/connection', { method: 'DELETE' })
            if (!response.ok) throw new Error('Unable to disconnect Dhan')
            setConfirmDisconnect(false); setClientId(''); setAutoRenew(false); setEditing(true)
            await load()
            window.dispatchEvent(new CustomEvent('dhan-connection-change', { detail: { connected: false } }))
        } catch (e) { setError(e instanceof Error ? e.message : 'Unable to disconnect') }
        finally { setState('idle') }
    }
    const busy = state !== 'idle'
    const fresh = connection?.lastCheckedAt && Date.now() - Date.parse(connection.lastCheckedAt) < 10 * 60_000
    const valid = connection?.tokenExpiresAt && Date.parse(connection.tokenExpiresAt) > Date.now()
    const ready = connection?.authStatus === 'ready' && fresh && valid
    const status = !connection?.connected ? 'Not connected' : ready ? 'Ready for trading' : !fresh ? 'Awaiting backend check' : connection.authStatus === 'pending' ? 'Verification pending' : 'Needs attention'
    const inputClass = 'mt-2 min-h-11 w-full rounded-xl border border-line bg-surface px-3 text-sm text-ink-primary outline-none focus-visible:ring-2 focus-visible:ring-ink-secondary'
    if (state === 'loading') return <p role="status" className="py-10 text-sm text-ink-secondary">Loading authentication…</p>

    return <div className="space-y-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
            <div><h3 ref={heading} tabIndex={-1} className="text-lg font-medium text-ink-primary outline-none">Dhan trading account</h3><p className="mt-1 text-xs text-ink-secondary">{connection?.dhanClientId ? 'Client ID ' + connection.dhanClientId : 'Connect your account for order execution.'}</p></div>
            <span className={'rounded-full border px-3 py-1.5 text-xs ' + (ready ? 'border-positive/30 text-positive' : 'border-line text-ink-secondary')}>{status}</span>
        </div>
        {error && <p role="alert" className="text-sm text-negative">{error}</p>}
        {message && <p role="status" className="text-sm text-positive">{message}</p>}
        {connection?.authError && <p className="text-sm text-warning">{reasons[connection.authError] || 'Authentication needs attention. Check your credentials and backend status.'}</p>}
        {connection?.connected && <>
            <dl className="grid grid-cols-1 gap-x-6 gap-y-4 border-y border-line py-5 sm:grid-cols-2">
                {[
                    ['Token expires', timestamp(connection.tokenExpiresAt)],
                    ['Next renewal', connection.autoRenew ? timestamp(connection.nextRenewalAt) : 'Automatic renewal is off'],
                    ['Last broker check', timestamp(connection.lastCheckedAt)],
                    ['Renewal', connection.renewalOwner === 'scanner' ? 'Managed with the shared data account' : connection.autoRenew ? 'Every 12 hours, with early expiry checks' : 'Manual'],
                ].map(([label, value]) => <div key={label}><dt className="text-xs text-ink-secondary">{label}</dt><dd className="mt-1.5 text-sm text-ink-primary">{value}</dd></div>)}
            </dl>
            <p className="text-xs leading-relaxed text-ink-secondary">Trading continues when you close the website or sign out. Dhan must still accept the account’s token and registered IP.</p>
        </>}
        <div className="space-y-3">
            <CopyValue label="Server IP to register with Dhan" value={connection?.staticIp} />
            <p className="text-xs text-ink-tertiary">Last IP check: {timestamp(connection?.ipCheckedAt)}</p>
            <CopyValue label="Dhan callback URL" value={connection?.redirectUrl} />
        </div>
        {!editing && <div className="flex flex-wrap gap-2">
            <Button onClick={() => { setEditing(true); setAutoRenew(connection?.autoRenew || false) }}>Edit authentication</Button>
            {connection?.renewalOwner !== 'scanner' && <Button onClick={() => void reconnect()} disabled={busy}>Reconnect with Dhan</Button>}
        </div>}
        {editing && <form onSubmit={save} className="space-y-5 border-t border-line pt-5">
            <div><h4 className="text-sm font-medium">Account credentials</h4><p className="mt-1 text-xs leading-relaxed text-ink-secondary">Secrets are encrypted on the server and never displayed again. Leave a saved field blank to keep it.</p></div>
            <label className="block text-xs text-ink-secondary">Client ID<input name="clientId" autoFocus required value={clientId} onChange={e => setClientId(e.target.value)} readOnly={connection?.connected} inputMode="numeric" className={inputClass} /></label>
            <div className="grid gap-4 sm:grid-cols-2">
                <label className="block text-xs text-ink-secondary">API key<input name="apiKey" type="password" required={!connection?.connected} autoComplete="new-password" className={inputClass} /></label>
                <label className="block text-xs text-ink-secondary">API secret<input name="apiSecret" type="password" required={!connection?.connected} autoComplete="new-password" className={inputClass} /></label>
            </div>
            <label className="block text-xs text-ink-secondary">Dhan Web access token<input name="accessToken" type="password" required={!connection?.connected} autoComplete="new-password" className={inputClass} /><span className="mt-2 block">Generate this in Dhan Web → DhanHQ Trading APIs. Its account and expiry are checked before saving.</span></label>
            {connection?.renewalOwner !== 'scanner' && <>
                <label className="flex min-h-11 items-center gap-3 text-sm"><input type="checkbox" checked={autoRenew} onChange={e => setAutoRenew(e.target.checked)} className="h-4 w-4 accent-current" />Allow automatic renewal and recovery</label>
                <p className="text-xs leading-relaxed text-ink-secondary">For recovery after an expired or rejected token, save your Dhan PIN and TOTP setup secret. Use the secret from TOTP setup, not the changing six-digit code. These credentials let the backend authenticate while you are offline.</p>
                <div className="grid gap-4 sm:grid-cols-2">
                    <label className="block text-xs text-ink-secondary">Dhan PIN<input name="pin" type="password" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} autoComplete="new-password" className={inputClass} /></label>
                    <label className="block text-xs text-ink-secondary">TOTP setup secret<input name="totpSecret" type="password" autoComplete="new-password" className={inputClass} /></label>
                </div>
                {connection?.recoveryConfigured && <label className="flex min-h-11 items-center gap-3 text-xs text-ink-secondary"><input type="checkbox" name="clearRecovery" />Remove saved PIN and TOTP secret</label>}
            </>}
            <div className="flex gap-2"><Button type="submit" variant="positive" disabled={busy}>{state === 'saving' ? 'Saving…' : 'Save authentication'}</Button>{connection?.connected && <Button type="button" onClick={() => { setEditing(false); heading.current?.focus() }} disabled={busy}>Cancel</Button>}</div>
        </form>}
        {connection?.connected && <div className="border-t border-line pt-5">
            {confirmDisconnect ? <div className="space-y-3"><p className="text-sm text-ink-secondary">Remove saved Dhan credentials and stop new order dispatch for this account?</p><div className="flex gap-2"><Button variant="danger" disabled={busy} onClick={() => void disconnect()}>Disconnect account</Button><Button disabled={busy} onClick={() => setConfirmDisconnect(false)}>Keep connected</Button></div></div>
                : <button type="button" className="min-h-11 text-xs text-negative" onClick={() => setConfirmDisconnect(true)}>Disconnect Dhan account</button>}
        </div>}
    </div>
}
