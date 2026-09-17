'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { AppearanceControl } from '@/components/theme/appearance-control'
import { Modal } from '@/components/motion/modal'
import { ChevronUpDown, Close } from '@/components/ui/icons'
import { createClient } from '@/lib/supabase/client'
import { Button } from '@/components/ui/button'
import DhanConnect from '@/components/dhan-connect'
import { initialsFor } from './identity'

type Section = 'Account' | 'Authentication' | 'Appearance'
const sections: Section[] = ['Account', 'Authentication', 'Appearance']

export function AccountMenu({ email }: { email?: string | null }) {
    const [open, setOpen] = useState(false)
    const [section, setSection] = useState<Section>('Account')
    const [signingOut, setSigningOut] = useState(false)
    const [error, setError] = useState('')
    const router = useRouter()
    useEffect(() => {
        const show = () => { setSection('Authentication'); setOpen(true) }
        window.addEventListener('open-authentication', show)
        return () => window.removeEventListener('open-authentication', show)
    }, [])
    const signOut = async () => {
        setSigningOut(true); setError('')
        try {
            const { error } = await createClient().auth.signOut()
            if (error) throw error
            router.push('/'); router.refresh()
        } catch { setError('Unable to sign out. Try again.') }
        finally { setSigningOut(false) }
    }
    return <>
        <button type="button" onClick={() => setOpen(true)} aria-haspopup="dialog" aria-expanded={open} aria-label="Open profile and settings"
            className="flex min-h-11 items-center gap-2 rounded-xl border border-line px-2 hover:bg-surface-hover focus-visible:outline focus-visible:outline-2">
            <span className="identity-tile h-7 w-7 text-[10px]">{initialsFor(email)}</span><ChevronUpDown size={13} className="text-ink-secondary" />
        </button>
        <Modal open={open} onClose={() => setOpen(false)} labelledBy="profile-title" size="wide">
            <div className="flex max-h-[min(820px,90dvh)] flex-col overflow-hidden rounded-2xl">
                <header className="flex shrink-0 items-center justify-between border-b border-line px-5 py-4 sm:px-7">
                    <div><h2 id="profile-title" className="text-lg font-medium text-ink-primary">Profile & settings</h2><p className="mt-1 text-xs text-ink-secondary">Your account, broker access and preferences</p></div>
                    <button type="button" onClick={() => setOpen(false)} aria-label="Close profile" className="grid h-11 w-11 shrink-0 place-items-center rounded-xl text-ink-secondary hover:bg-surface-hover"><Close size={18} /></button>
                </header>
                <div className="flex min-h-0 flex-1 flex-col sm:flex-row">
                    <nav aria-label="Profile sections" className="flex shrink-0 gap-1 border-b border-line p-3 sm:w-44 sm:flex-col sm:border-b-0 sm:border-r sm:p-4">
                        {sections.map(item => <button key={item} type="button" aria-current={item === section ? 'page' : undefined} onClick={() => setSection(item)}
                            className={'min-h-11 rounded-xl px-3 text-left text-xs sm:text-sm ' + (section === item ? 'bg-surface-strong font-medium text-ink-primary' : 'text-ink-secondary hover:bg-surface-hover')}>{item}</button>)}
                    </nav>
                    <div className="min-h-0 min-w-0 flex-1 overflow-y-auto p-5 sm:p-7">
                        {open && section === 'Authentication' && <DhanConnect />}
                        {section === 'Account' && <div className="space-y-6">
                            <div className="flex items-center gap-4"><span className="identity-tile h-14 w-14 text-lg">{initialsFor(email)}</span><div className="min-w-0"><p className="text-xs text-ink-secondary">Signed in as</p><p className="mt-1 break-all text-sm text-ink-primary">{email || 'Account details unavailable'}</p></div></div>
                            <div className="border-y border-line py-5"><h3 className="text-sm font-medium">Broker authentication</h3><p className="mt-2 text-sm leading-relaxed text-ink-secondary">Manage your Dhan credentials, automatic renewal and server IP.</p><Button className="mt-4" onClick={() => setSection('Authentication')}>Manage authentication</Button></div>
                            <div className="flex flex-wrap gap-5 text-xs text-ink-secondary"><Link href="/privacy-policy" onClick={() => setOpen(false)}>Privacy policy</Link><Link href="/terms-of-service" onClick={() => setOpen(false)}>Terms of service</Link></div>
                            <div><p className="mb-3 text-xs text-ink-secondary">Signing out of the website does not disable backend trading.</p><Button variant="danger" disabled={signingOut} onClick={() => void signOut()}>{signingOut ? 'Signing out…' : 'Sign out'}</Button>{error && <p role="alert" className="mt-3 text-xs text-negative">{error}</p>}</div>
                        </div>}
                        {section === 'Appearance' && <div><h3 id="profile-appearance" className="mb-4 text-sm font-medium">Appearance</h3><AppearanceControl labelledBy="profile-appearance" /></div>}
                    </div>
                </div>
            </div>
        </Modal>
    </>
}
