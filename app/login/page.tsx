'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
import { AuthDivider, AuthShell } from '@/components/auth/auth-shell'
import { AuthField, AuthSubmit, GoogleButton } from '@/components/auth/auth-form'
import { ErrorMessage, useErrorShake } from '@/components/motion/error-field'

/**
 * Sign in.
 *
 * Motion. The frame's staggered entrance comes from `AuthShell`; what belongs to
 * this page is the failure path.
 *
 * A rejected credential now shakes the form and reveals its message beneath it
 * (recipe 12) rather than inserting a red panel above the fields. That panel had
 * two problems: it appeared 200px away from the field the user was looking at,
 * and inserting it pushed the whole form down, so the input under the cursor
 * moved at the exact moment the user went to correct it. The shake keeps the
 * layout still and puts the feedback where the problem is.
 *
 * The message element stays mounted with a non-breaking space holding its line,
 * which is what keeps the fields from shifting when an error arrives or clears.
 * Typing cancels the auto-revert, so the user is never shaking at a value they
 * are already fixing.
 */
export default function LoginPage() {
    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const form = useErrorShake<HTMLFormElement>()
    const router = useRouter()
    const supabase = createClient()

    useEffect(() => {
        if (new URLSearchParams(window.location.search).get('error') === 'auth_unavailable') {
            setError('Authentication is temporarily unavailable. Please try again shortly.')
            form.trigger()
        }
        // Runs once on mount; `form` is stable for the life of the hook.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [])

    const fail = (message: string) => {
        setError(message)
        form.trigger()
        setLoading(false)
    }

    /** Clears the error the moment the user starts correcting the input. */
    const edit = (setter: (value: string) => void) => (value: string) => {
        setter(value)
        if (error) {
            setError(null)
            form.clear()
        }
    }

    const handleLogin = async (event: React.FormEvent) => {
        event.preventDefault()
        setLoading(true)
        setError(null)
        form.clear()

        const { error: signInError } = await supabase.auth.signInWithPassword({ email, password })

        if (signInError) {
            fail(signInError.message)
            return
        }
        router.push('/dashboard')
        router.refresh()
    }

    const handleGoogleLogin = async () => {
        setLoading(true)
        setError(null)
        form.clear()

        const { error: oauthError } = await supabase.auth.signInWithOAuth({
            provider: 'google',
            options: { redirectTo: `${window.location.origin}/auth/callback` },
        })

        if (oauthError) fail(oauthError.message)
    }

    return (
        <AuthShell
            eyebrow={
                <>
                    <span className="relative flex h-1.5 w-1.5">
                        <span className="absolute inline-flex h-full w-full animate-pulse-ring rounded-full bg-success opacity-60" />
                        <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-success" />
                    </span>
                    <span className="font-mono text-[11px] uppercase tracking-[0.22em] text-white/60">
                        Secure session
                    </span>
                </>
            }
            title={
                <>
                    Welcome <span className="font-serif-italic text-white/80">back.</span>
                </>
            }
            subtitle="Sign in to access your autonomous trading intelligence."
            footer={
                <>
                    New to PolyCognition?{' '}
                    <Link
                        href="/signup"
                        className="text-white underline-offset-4 transition-colors duration-[250ms] hover:text-accent hover:underline"
                    >
                        Create an account
                    </Link>
                </>
            }
        >
            <div className={form.wrapClass}>
                <form
                    ref={form.fieldRef}
                    onSubmit={handleLogin}
                    className={`${form.fieldClass} flex flex-col gap-5 !border-0`}
                    noValidate
                >
                    <AuthField
                        id="email"
                        label="Email"
                        type="email"
                        value={email}
                        onChange={(event) => edit(setEmail)(event.target.value)}
                        required
                        autoComplete="email"
                        placeholder="you@example.com"
                        aria-invalid={form.errored}
                        aria-describedby="login-error"
                    />

                    <AuthField
                        id="password"
                        label="Password"
                        type="password"
                        value={password}
                        onChange={(event) => edit(setPassword)(event.target.value)}
                        required
                        autoComplete="current-password"
                        placeholder="••••••••"
                        aria-invalid={form.errored}
                        aria-describedby="login-error"
                    />

                    <AuthSubmit pending={loading} pendingLabel="Signing in">
                        Sign in
                    </AuthSubmit>
                </form>

                <ErrorMessage id="login-error">{error}</ErrorMessage>
            </div>

            <AuthDivider />

            <GoogleButton onClick={handleGoogleLogin} disabled={loading} label="Continue with Google" />
        </AuthShell>
    )
}
