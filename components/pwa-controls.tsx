'use client'

import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'

interface InstallPrompt extends Event {
    prompt: () => Promise<void>
    userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

function isInstallPrompt(event: Event): event is InstallPrompt {
    return 'prompt' in event && typeof event.prompt === 'function' && 'userChoice' in event
}

export function PwaControls() {
    const [install, setInstall] = useState<InstallPrompt | null>(null)
    const [waiting, setWaiting] = useState<ServiceWorker | null>(null)
    const [offline, setOffline] = useState(false)
    const [help, setHelp] = useState(false)
    const [installed, setInstalled] = useState(false)
    const [error, setError] = useState<string | null>(null)
    useEffect(() => {
        const connection = () => setOffline(!navigator.onLine)
        const prompt = (event: Event) => { if (isInstallPrompt(event)) { event.preventDefault(); setInstall(event) } }
        const done = () => { setInstall(null); setInstalled(true); setHelp(false) }
        connection()
        setInstalled(window.matchMedia('(display-mode: standalone)').matches)
        window.addEventListener('online', connection)
        window.addEventListener('offline', connection)
        window.addEventListener('beforeinstallprompt', prompt)
        window.addEventListener('appinstalled', done)
        let disposed = false
        let registration: ServiceWorkerRegistration | undefined
        let worker: ServiceWorker | null = null
        const changed = () => { if (!disposed && worker?.state === 'installed' && navigator.serviceWorker.controller) setWaiting(registration?.waiting || null) }
        const found = () => { worker?.removeEventListener('statechange', changed); worker = registration?.installing || null; worker?.addEventListener('statechange', changed) }
        if ('serviceWorker' in navigator && process.env.NODE_ENV === 'production') {
            void navigator.serviceWorker.register('/sw.js', { scope: '/', updateViaCache: 'none' }).then((value) => {
                if (disposed) return
                registration = value
                setWaiting(value.waiting)
                value.addEventListener('updatefound', found)
                found()
            }).catch(() => { if (!disposed) setError('App installation is unavailable. You can continue in this browser.') })
        }
        return () => {
            disposed = true
            window.removeEventListener('online', connection); window.removeEventListener('offline', connection)
            window.removeEventListener('beforeinstallprompt', prompt); window.removeEventListener('appinstalled', done)
            registration?.removeEventListener('updatefound', found); worker?.removeEventListener('statechange', changed)
        }
    }, [])
    const installApp = async () => {
        if (!install) { setHelp(!help); return }
        try { await install.prompt(); await install.userChoice; setInstall(null) }
        catch { setError('Installation did not open. Use your browser menu to install the app.') }
    }
    return <>
        {!installed && <Button className="pwa-install" aria-label="Install app" onClick={() => void installApp()}>
            <svg aria-hidden width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M12 3v12m-4-4 4 4 4-4M5 16v5h14v-5" /></svg>
            <span className="hidden lg:inline">Install app</span>
        </Button>}
        {(offline || waiting || help || error) && <div className="pwa-message" role="status">
            {offline && <p>You are offline. Balances and agent activity may be out of date.</p>}
            {help && <p>On iPhone or iPad, open Share, then Add to Home Screen. On Android or desktop, use Install app in the browser menu when available.</p>}
            {error && <p>{error}</p>}
            {waiting && <Button onClick={() => {
                navigator.serviceWorker.addEventListener('controllerchange', () => window.location.reload(), { once: true })
                waiting.postMessage({ type: 'ACTIVATE_UPDATE' })
            }}>Update app and reload</Button>}
            {(help || error) && <Button onClick={() => { setHelp(false); setError(null) }}>Dismiss</Button>}
        </div>}
    </>
}
