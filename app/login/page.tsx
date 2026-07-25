"use client";

import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";

const ease = [0.16, 1, 0.3, 1] as const;

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const supabase = createClient();

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("error") === "auth_unavailable") {
      setError("Authentication is temporarily unavailable. Please try again shortly.");
    }
  }, []);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    const { error } = await supabase.auth.signInWithPassword({
      email,
      password,
    });

    if (error) {
      setError(error.message);
      setLoading(false);
    } else {
      router.push("/dashboard");
      router.refresh();
    }
  };

  const handleGoogleLogin = async () => {
    setLoading(true);
    setError(null);

    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${window.location.origin}/auth/callback`,
      },
    });

    if (error) {
      setError(error.message);
      setLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen w-full bg-[#050505] overflow-hidden">
      {/* Ambient backdrop */}
      <div className="absolute inset-0 bg-grid-fine opacity-50" />
      <div className="absolute inset-0 bg-spotlight" />
      <div className="absolute -top-40 -left-40 w-[500px] h-[500px] bg-accent/[0.06] rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute -bottom-40 -right-40 w-[500px] h-[500px] bg-success/[0.04] rounded-full blur-[120px] pointer-events-none" />

      {/* Top bar with logo + back link */}
      <header className="relative z-10 mx-auto max-w-7xl px-6 lg:px-8 py-6 flex items-center justify-between">
        <Link href="/" className="group flex items-center gap-2.5">
          <div className="relative h-7 w-7">
            <div className="absolute inset-0 rounded-full bg-gradient-to-br from-accent to-success opacity-80 blur-md group-hover:opacity-100 transition-opacity" />
            <div className="absolute inset-[3px] rounded-full bg-[#0a0a0c] flex items-center justify-center">
              <div className="h-1.5 w-1.5 rounded-full bg-white" />
            </div>
          </div>
          <span className="text-[15px] font-medium tracking-[-0.02em] text-white">
            Aetheria
          </span>
        </Link>
        <Link
          href="/"
          className="text-[12px] text-white/50 hover:text-white transition-colors tracking-[-0.01em]"
        >
          ← Back to home
        </Link>
      </header>

      {/* Form panel */}
      <main className="relative z-10 flex items-center justify-center px-6 py-12 sm:py-20">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease }}
          className="w-full max-w-md"
        >
          {/* Eyebrow */}
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease, delay: 0.1 }}
            className="inline-flex items-center gap-2 mb-6"
          >
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full rounded-full bg-success opacity-60 animate-pulse-ring" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-success" />
            </span>
            <span className="text-[11px] font-mono uppercase tracking-[0.22em] text-white/60">
              Secure session
            </span>
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, ease, delay: 0.15 }}
            className="font-display text-[44px] sm:text-[52px] text-white tracking-[-0.035em] leading-[0.95] mb-3"
          >
            Welcome{" "}
            <span className="font-serif-italic text-white/80">back.</span>
          </motion.h1>
          <motion.p
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, ease, delay: 0.2 }}
            className="text-[14px] text-ink-secondary mb-10"
          >
            Sign in to access your autonomous trading intelligence.
          </motion.p>

          {/* Card */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease, delay: 0.25 }}
            className="surface rounded-2xl p-7 sm:p-8"
          >
            {error && (
              <div className="mb-6 rounded-lg border border-danger/30 bg-danger/[0.08] px-4 py-3">
                <p className="text-[13px] text-danger">{error}</p>
              </div>
            )}

            <form onSubmit={handleLogin} className="flex flex-col gap-5">
              <div>
                <label
                  htmlFor="email"
                  className="block text-[11px] font-mono uppercase tracking-[0.18em] text-ink-tertiary mb-2"
                >
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="w-full bg-[#0a0a0c] border border-line rounded-lg px-4 py-3 text-[14px] text-white placeholder-ink-tertiary outline-none focus:border-accent/50 focus:bg-[#0c0c0e] transition-colors"
                  placeholder="you@example.com"
                />
              </div>

              <div>
                <label
                  htmlFor="password"
                  className="block text-[11px] font-mono uppercase tracking-[0.18em] text-ink-tertiary mb-2"
                >
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="w-full bg-[#0a0a0c] border border-line rounded-lg px-4 py-3 text-[14px] text-white placeholder-ink-tertiary outline-none focus:border-accent/50 focus:bg-[#0c0c0e] transition-colors"
                  placeholder="••••••••"
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="group mt-2 relative inline-flex items-center justify-center gap-2 rounded-full bg-white px-5 py-3.5 text-[14px] font-medium text-black transition-all duration-500 ease-out-expo hover:shadow-[0_0_32px_rgba(255,255,255,0.18)] hover:-translate-y-0.5 disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none"
              >
                {loading ? (
                  <>
                    <svg
                      className="animate-spin h-4 w-4"
                      viewBox="0 0 24 24"
                      fill="none"
                    >
                      <circle
                        className="opacity-25"
                        cx="12"
                        cy="12"
                        r="10"
                        stroke="currentColor"
                        strokeWidth="3"
                      />
                      <path
                        className="opacity-75"
                        fill="currentColor"
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                      />
                    </svg>
                    <span>Signing in…</span>
                  </>
                ) : (
                  <>
                    <span>Sign in</span>
                    <span className="inline-block transition-transform duration-300 group-hover:translate-x-0.5">
                      →
                    </span>
                  </>
                )}
              </button>
            </form>

            {/* Divider */}
            <div className="relative my-6">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-line" />
              </div>
              <div className="relative flex justify-center">
                <span className="px-3 bg-[#0E0E10] text-[10px] font-mono uppercase tracking-[0.22em] text-ink-tertiary">
                  or
                </span>
              </div>
            </div>

            {/* Google */}
            <button
              type="button"
              onClick={handleGoogleLogin}
              disabled={loading}
              className="w-full inline-flex items-center justify-center gap-2.5 rounded-full border border-line bg-white/[0.02] backdrop-blur-sm px-5 py-3 text-[14px] font-medium text-white transition-all duration-500 ease-out-expo hover:bg-white/[0.06] hover:border-white/20 disabled:opacity-50"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24">
                <path
                  fill="#4285F4"
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                />
                <path
                  fill="#34A853"
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                />
                <path
                  fill="#FBBC05"
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                />
                <path
                  fill="#EA4335"
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                />
              </svg>
              <span>Continue with Google</span>
            </button>
          </motion.div>

          {/* Footer link */}
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.6, ease, delay: 0.5 }}
            className="text-center text-[13px] text-ink-secondary mt-8"
          >
            New to Aetheria?{" "}
            <Link
              href="/signup"
              className="text-white hover:text-accent transition-colors underline-offset-4 hover:underline"
            >
              Create an account
            </Link>
          </motion.p>
        </motion.div>
      </main>
    </div>
  );
}
