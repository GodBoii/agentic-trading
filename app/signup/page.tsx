'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
import { AuthDivider, AuthShell } from '@/components/auth/auth-shell'
import { AuthField, AuthSubmit, GoogleButton } from '@/components/auth/auth-form'
import { ErrorMessage, useErrorShake } from '@/components/motion/error-field'
import { Reveal } from '@/components/motion/reveal'
import { SuccessBadge } from '@/components/motion/success-check'

/**
 * Create an account.
 *
 * Motion. Two moments carry it, and both are real state changes:
 *
 *   - Validation failure shakes the form and reveals the message beneath it
 *     (recipe 12). This page has two client-side rules — passwords matching and
 *     a minimum length — which fire instantly, with no network round trip. That
 *     is precisely the case where a static message is easiest to miss: nothing
 *     else on the screen changes, so without the shake a mistyped confirmation
 *     just appears to do nothing when submitted.
 *
 *   - Success draws a check (recipe 10): the badge fades in, rotates upright,
 *     settles with a bob, and the tick strokes itself over 500ms. This replaced
 *     a static SVG checkmark inside a circle. It is worth the ceremony here
 *     because it is the one genuinely celebratory moment in the product, and
 *     because the screen it announces is a dead end that redirects — the draw
 *     gives the user something to read the outcome from before the page moves.
 */
export default function SignUpPage() {
    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')
    const [confirmPassword, setConfirmPassword] = useState('')
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [success, setSuccess] = useState(false)
    const form = useErrorShake<HTMLFormElement>()
    const router = useRouter()
    const supabase = createClient()

    const fail = (message: string) => {
        setError(message)
        form.trigger()
        setLoading(false)
    }

    const edit = (setter: (value: string) => void) => (value: string) => {
        setter(value)
        if (error) {
            setError(null)
            form.clear()
        }
    }

    const handleSignUp = async (event: React.FormEvent) => {
        event.preventDefault()
        setLoading(true)
        setError(null)
        form.clear()

        if (password !== confirmPassword) {
            fail('Passwords do not match.')
            return
        }
        if (password.length < 6) {
            fail('Password must be at least 6 characters.')
            return
        }

        const { error: signUpError } = await supabase.auth.signUp({
            email,
            password,
            options: { emailRedirectTo: `${window.location.origin}/auth/callback` },
        })

        if (signUpError) {
            fail(signUpError.message)
            return
        }

        setSuccess(true)
        setLoading(false)
        setTimeout(() => router.push('/login'), 3000)
    }

    const handleGoogleSignUp = async () => {
        setLoading(true)
        setError(null)
        form.clear()

        const { error: oauthError } = await supabase.auth.signInWithOAuth({
            provider: 'google',
            options: { redirectTo: `${window.location.origin}/auth/callback` },
        })

        if (oauthError) fail(oauthError.message)
    }

    if (success) {
        return (
            <div className="relative flex min-h-screen w-full items-center justify-center overflow-hidden bg-[#050505]">
                <div className="absolute inset-0 bg-grid-fine opacity-50" />
                <div className="absolute inset-0 bg-spotlight" />

                <Reveal immediate className="relative z-10 w-full max-w-md px-6">
                    <div className="surface rounded-2xl p-10 text-center">
                        {/* The check draws itself as the panel lands, so the
                            outcome reads as earned rather than pre-printed. */}
                        <SuccessBadge size={64} className="mx-auto mb-6" />
                        <h1 className="mb-3 font-display text-[32px] tracking-[-0.025em] text-white">
                            Account <span className="font-serif-italic text-white/80">created.</span>
                        </h1>
                        <p className="text-[14px] leading-relaxed text-ink-secondary">
                            Check your email to verify your account. Redirecting to sign in…
                        </p>
                        <div className="mt-8 flex items-center justify-center gap-2 font-mono text-[11px] uppercase tracking-[0.18em] text-ink-tertiary">
                            <span className="relative flex h-1.5 w-1.5">
                                <span className="absolute inline-flex h-full w-full animate-pulse-ring rounded-full bg-accent opacity-60" />
                                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-accent" />
                            </span>
                            Verifying
                        </div>
                    </div>
                </Reveal>
            </div>
        )
    }

    return (
        <AuthShell
            eyebrow={
                <>
                    <span className="h-px w-8 bg-accent" />
                    <span className="font-mono text-[11px] uppercase tracking-[0.22em] text-accent">Get started</span>
                </>
            }
            title={
                <>
                    Deploy your <span className="font-serif-italic text-white/80">first agent.</span>
                </>
            }
            subtitle="Create your account to begin autonomous trading in under 60 seconds."
            footer={
                <>
                    Already have an account?{' '}
                    <Link
                        href="/login"
                        className="text-white underline-offset-4 transition-colors duration-[250ms] hover:text-accent hover:underline"
                    >
                        Sign in
                    </Link>
                </>
            }
        >
            <div className={form.wrapClass}>
                <form
                    ref={form.fieldRef}
                    onSubmit={handleSignUp}
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
                        aria-describedby="signup-error"
                    />

                    <AuthField
                        id="password"
                        label="Password"
                        type="password"
                        value={password}
                        onChange={(event) => edit(setPassword)(event.target.value)}
                        required
                        autoComplete="new-password"
                        placeholder="At least 6 characters"
                        aria-invalid={form.errored}
                        aria-describedby="signup-error"
                    />

                    <AuthField
                        id="confirmPassword"
                        label="Confirm password"
                        type="password"
                        value={confirmPassword}
                        onChange={(event) => edit(setConfirmPassword)(event.target.value)}
                        required
                        autoComplete="new-password"
                        placeholder="Repeat password"
                        aria-invalid={form.errored}
                        aria-describedby="signup-error"
                    />

                    <AuthSubmit pending={loading} pendingLabel="Creating account">
                        Create account
                    </AuthSubmit>
                </form>

                <ErrorMessage id="signup-error">{error}</ErrorMessage>
            </div>

            <AuthDivider />

            <GoogleButton onClick={handleGoogleSignUp} disabled={loading} label="Continue with Google" />
        </AuthShell>
    )
}
