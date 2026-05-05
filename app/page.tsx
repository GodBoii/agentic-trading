import Link from 'next/link'
import { createClient } from '@/lib/supabase/server'
import ArchitectureSVG from '@/components/architecture-svg'

export const metadata = {
    title: 'Agentic Trading — AI-Powered Trading Platform',
    description: 'Multi-agent AI system that analyzes markets 24/7 and executes profitable trades automatically on your Dhan account.',
}

export default async function HomePage() {
    const supabase = await createClient()
    const { data: { user } } = await supabase.auth.getUser()

    return (
        <div className="min-h-screen bg-brutal-black">
            {/* ─── NAVBAR ─── */}
            <header className="bg-brutal-black border-b-4 border-brutal-white sticky top-0 z-40">
                <div className="max-w-7xl mx-auto px-6 lg:px-8 py-5">
                    <div className="flex items-center justify-between">
                        {/* Logo */}
                        <div className="flex items-center gap-4">
                            <div className="w-12 h-12 bg-brutal-cream border-4 border-brutal-black flex items-center justify-center p-1.5">
                                <img src="/icon.png" alt="Agentic Trading Logo" className="w-full h-full object-contain" />
                            </div>
                            <div>
                                <span className="text-2xl font-bold text-brutal-cream uppercase tracking-tight">
                                    Agentic Trading
                                </span>
                                <p className="text-brutal-cream/50 font-mono text-xs uppercase tracking-widest hidden sm:block">
                                    AI-Powered Platform
                                </p>
                            </div>
                        </div>

                        {/* Nav Actions */}
                        <nav className="flex items-center gap-4">
                            {user ? (
                                <Link
                                    href="/dashboard"
                                    id="nav-dashboard-btn"
                                    className="brutal-btn px-6 py-3 text-sm"
                                    aria-label="Go to your trading dashboard"
                                >
                                    Dashboard →
                                </Link>
                            ) : (
                                <>
                                    <Link
                                        href="/login"
                                        id="nav-signin-btn"
                                        className="text-brutal-cream font-bold uppercase tracking-wider text-sm border-b-2 border-transparent hover:border-brutal-cream transition-all"
                                        aria-label="Sign in to your account"
                                    >
                                        Sign In
                                    </Link>
                                    <Link
                                        href="/signup"
                                        id="nav-signup-btn"
                                        className="brutal-btn px-6 py-3 text-sm"
                                        aria-label="Create a new account"
                                    >
                                        Sign Up
                                    </Link>
                                </>
                            )}
                        </nav>
                    </div>
                </div>
            </header>

            <main>
                {/* ─── HERO ─── */}
                <section className="max-w-7xl mx-auto px-6 lg:px-8 pt-24 pb-20">
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 items-center">
                        <div className="space-y-8 animate-pop">
                            <div className="inline-flex items-center gap-3 brutal-box-sm px-4 py-2">
                                <div className="w-2 h-2 bg-brutal-green animate-pulse" />
                                <span className="font-mono text-xs text-brutal-cream uppercase tracking-widest">
                                    System Online — AI Markets Active
                                </span>
                            </div>

                            <h1 className="text-6xl lg:text-7xl font-bold text-brutal-cream uppercase leading-none tracking-tight">
                                Trade
                                <br />
                                <span className="text-brutal-green">Smarter</span>
                                <br />
                                With AI
                            </h1>

                            <p className="text-brutal-cream/70 font-mono text-lg leading-relaxed max-w-lg">
                                A multi-agent AI system that monitors BSE / NSE markets 24 × 7, performs
                                technical &amp; sentiment analysis, and executes profitable trades automatically
                                on your Dhan account.
                            </p>

                            <div className="flex flex-col sm:flex-row gap-4">
                                {user ? (
                                    <Link
                                        href="/dashboard"
                                        id="hero-dashboard-btn"
                                        className="brutal-btn px-8 py-4 text-base text-center"
                                        aria-label="Open your trading dashboard"
                                    >
                                        Open Dashboard →
                                    </Link>
                                ) : (
                                    <>
                                        <Link
                                            href="/signup"
                                            id="hero-signup-btn"
                                            className="brutal-btn px-8 py-4 text-base text-center"
                                            aria-label="Get started for free"
                                        >
                                            Get Started Free
                                        </Link>
                                        <Link
                                            href="/login"
                                            id="hero-signin-btn"
                                            className="bg-brutal-black border-4 border-brutal-white text-brutal-cream font-bold py-4 px-8 transition-all transform hover:translate-x-1 hover:translate-y-1 hover:shadow-brutal-sm active:translate-x-2 active:translate-y-2 active:shadow-none shadow-brutal uppercase tracking-wider text-sm text-center"
                                            aria-label="Sign in to your account"
                                        >
                                            Sign In
                                        </Link>
                                    </>
                                )}
                            </div>
                        </div>

                        {/* Hero Stats Panel */}
                        <div className="space-y-4 animate-pop">
                            <div className="brutal-box p-8">
                                <div className="flex items-center justify-between mb-6">
                                    <div className="flex items-center gap-3">
                                        <div className="w-3 h-3 bg-brutal-green" />
                                        <span className="font-mono text-sm text-brutal-cream/70 uppercase tracking-wider">AI Status</span>
                                    </div>
                                    <span className="font-mono text-xs bg-brutal-green text-brutal-black px-3 py-1 font-bold uppercase">
                                        Live
                                    </span>
                                </div>
                                <div className="grid grid-cols-2 gap-6">
                                    {[
                                        { label: 'Markets Monitored', value: '2', unit: 'Exchanges' },
                                        { label: 'Analysis Cycles', value: '24/7', unit: 'Always On' },
                                        { label: 'AI Agents', value: '5+', unit: 'Active' },
                                        { label: 'Security', value: 'AES', unit: 'Encrypted' },
                                    ].map((stat) => (
                                        <div key={stat.label} className="brutal-box-sm p-4">
                                            <p className="text-brutal-cream/50 font-mono text-xs uppercase tracking-wider mb-1">{stat.label}</p>
                                            <p className="text-3xl font-bold text-brutal-cream">{stat.value}</p>
                                            <p className="text-brutal-green font-mono text-xs uppercase mt-1">{stat.unit}</p>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            {/* Mini how-it-works teaser */}
                            <div className="brutal-box-sm p-6 border-brutal-green shadow-brutal-green">
                                <div className="flex gap-3 items-start">
                                    <div className="w-3 h-3 bg-brutal-green flex-shrink-0 mt-1" />
                                    <div>
                                        <p className="text-brutal-cream font-bold uppercase tracking-wide text-sm mb-1">Zero Manual Effort</p>
                                        <p className="text-brutal-cream/60 font-mono text-xs leading-relaxed">
                                            Connect your Dhan account once, flip the AI switch, and let the system
                                            do the rest — every single day.
                                        </p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </section>

                {/* ─── FEATURES ─── */}
                <section className="border-t-4 border-brutal-white bg-brutal-gray-900">
                    <div className="max-w-7xl mx-auto px-6 lg:px-8 py-20">
                        <div className="flex items-center gap-4 mb-12">
                            <div className="w-3 h-3 bg-brutal-cream" />
                            <h2 className="text-4xl font-bold text-brutal-cream uppercase tracking-tight">
                                What You Get
                            </h2>
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                            {[
                                {
                                    color: 'bg-brutal-green',
                                    title: 'AI-Powered',
                                    description: 'Multi-agent system runs technical, fundamental, and sentiment analysis simultaneously — 24 hours a day.',
                                },
                                {
                                    color: 'bg-brutal-cream',
                                    title: 'Secure',
                                    description: 'Bank-level AES encryption with Supabase Row-Level Security. We never see or store your Dhan password.',
                                },
                                {
                                    color: 'bg-brutal-yellow',
                                    title: 'Automated',
                                    description: 'Set it and forget it. The AI identifies opportunities and executes trades when conditions are right.',
                                },
                                {
                                    color: 'bg-brutal-red',
                                    title: 'Risk-Aware',
                                    description: 'Configurable position sizing, stop-loss automation, and portfolio exposure limits built in.',
                                },
                                {
                                    color: 'bg-[#7C3AED]',
                                    title: 'Real-Time',
                                    description: 'Live portfolio overview — funds, holdings, and open positions refreshed in real time from Dhan.',
                                },
                                {
                                    color: 'bg-brutal-green',
                                    title: 'Controllable',
                                    description: 'Toggle AI trading on or off any time from your dashboard. You stay in complete control.',
                                },
                            ].map((feature) => (
                                <div key={feature.title} className="brutal-box p-8 hover:translate-x-1 hover:translate-y-1 hover:shadow-brutal-sm transition-all">
                                    <div className="flex items-start gap-4 mb-4">
                                        <div className={`w-4 h-4 ${feature.color} flex-shrink-0 mt-1`} />
                                        <h3 className="text-2xl font-bold text-brutal-cream uppercase">{feature.title}</h3>
                                    </div>
                                    <p className="text-brutal-cream/70 leading-relaxed font-mono text-sm">{feature.description}</p>
                                </div>
                            ))}
                        </div>
                    </div>
                </section>

                {/* ─── HOW IT WORKS ─── */}
                <section className="border-t-4 border-brutal-white">
                    <div className="max-w-7xl mx-auto px-6 lg:px-8 py-20">
                        <div className="flex items-center gap-4 mb-12">
                            <div className="w-3 h-3 bg-brutal-yellow" />
                            <h2 className="text-4xl font-bold text-brutal-cream uppercase tracking-tight">
                                How It Works
                            </h2>
                        </div>
                        <div className="brutal-box-lg p-10">
                            <div className="space-y-10">
                                {[
                                    {
                                        num: '1',
                                        color: 'bg-brutal-cream',
                                        title: 'Create Account',
                                        desc: 'Sign up for free with your email or Google account. No credit card required.',
                                    },
                                    {
                                        num: '2',
                                        color: 'bg-brutal-green',
                                        title: 'Connect Dhan',
                                        desc: 'Enter your Dhan Client ID and securely link your trading account via OAuth.',
                                    },
                                    {
                                        num: '3',
                                        color: 'bg-brutal-yellow',
                                        title: 'Enable AI Trading',
                                        desc: 'Toggle the AI trading switch and let the multi-agent system start analyzing and trading.',
                                    },
                                    {
                                        num: '4',
                                        color: 'bg-[#7C3AED]',
                                        title: 'Monitor & Grow',
                                        desc: 'Track your funds, holdings, and positions in real time from the dashboard.',
                                    },
                                ].map((step, i) => (
                                    <div key={step.num} className="flex gap-6 items-start">
                                        <div className={`flex-shrink-0 w-12 h-12 ${step.color} text-brutal-black flex items-center justify-center font-bold text-xl border-3 border-brutal-black`}>
                                            {step.num}
                                        </div>
                                        <div className="flex-1 pt-2">
                                            <h4 className="font-bold text-brutal-cream mb-2 text-xl uppercase">{step.title}</h4>
                                            <p className="text-brutal-cream/70 font-mono">{step.desc}</p>
                                        </div>
                                        {i < 3 && (
                                            <div className="hidden lg:block flex-shrink-0 w-12 pt-6 text-brutal-cream/30 font-mono text-2xl text-center">
                                                ↓
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                </section>

                {/* ─── NEURAL PROCESSING CORE ─── */}
                <section className="border-t-4 border-brutal-white">
                    <div className="max-w-7xl mx-auto px-6 lg:px-8 py-20">
                        <div className="flex items-center gap-4 mb-8">
                            <div className="w-3 h-3 bg-[#7C3AED]" />
                            <h2 className="text-4xl font-bold text-brutal-cream uppercase tracking-tight">
                                Neural Processing Core
                            </h2>
                        </div>
                        <p className="text-brutal-cream/60 font-mono text-sm mb-8 max-w-3xl">
                            Live visualization of the multi-agent architecture — from BSE universe scanning through
                            momentum detection, regime analysis, and final trade execution via the Dhan API.
                        </p>
                        <ArchitectureSVG />
                    </div>
                </section>

                {/* ─── DASHBOARD PREVIEW TEASER ─── */}
                <section className="border-t-4 border-brutal-white bg-brutal-gray-900">
                    <div className="max-w-7xl mx-auto px-6 lg:px-8 py-20">
                        <div className="flex flex-col lg:flex-row gap-12 items-center">
                            <div className="flex-1 space-y-6">
                                <div className="flex items-center gap-4">
                                    <div className="w-3 h-3 bg-brutal-green" />
                                    <h2 className="text-4xl font-bold text-brutal-cream uppercase tracking-tight">
                                        Your Dashboard
                                    </h2>
                                </div>
                                <p className="text-brutal-cream/70 font-mono text-lg leading-relaxed">
                                    After signing in, your personalized dashboard gives you full control —
                                    connect Dhan, monitor trading status, view your portfolio, holdings, and open positions.
                                </p>
                                <ul className="space-y-3">
                                    {[
                                        'Connect to Dhan via secure OAuth',
                                        'Real-time Portfolio Overview (Funds, Holdings, Positions)',
                                        'AI Trading Status & Toggle Control',
                                        'Neural Architecture Visualizer',
                                    ].map((item) => (
                                        <li key={item} className="flex items-center gap-3 font-mono text-sm text-brutal-cream/80">
                                            <div className="w-2 h-2 bg-brutal-green flex-shrink-0" />
                                            {item}
                                        </li>
                                    ))}
                                </ul>
                                <div className="pt-4">
                                    {user ? (
                                        <Link href="/dashboard" id="teaser-dashboard-btn" className="brutal-btn px-8 py-4 text-base inline-block">
                                            Open Dashboard →
                                        </Link>
                                    ) : (
                                        <Link href="/signup" id="teaser-signup-btn" className="brutal-btn px-8 py-4 text-base inline-block">
                                            Start For Free →
                                        </Link>
                                    )}
                                </div>
                            </div>

                            {/* Mock dashboard preview */}
                            <div className="flex-1 w-full">
                                <div className="brutal-box p-6 space-y-4">
                                    <div className="flex items-center justify-between mb-2">
                                        <span className="font-mono text-xs text-brutal-cream/50 uppercase tracking-widest">Dashboard Preview</span>
                                        <div className="flex gap-2">
                                            <div className="w-3 h-3 bg-brutal-red border-2 border-brutal-black" />
                                            <div className="w-3 h-3 bg-brutal-yellow border-2 border-brutal-black" />
                                            <div className="w-3 h-3 bg-brutal-green border-2 border-brutal-black" />
                                        </div>
                                    </div>
                                    <div className="grid grid-cols-2 gap-3">
                                        {/* Dhan Connect mock */}
                                        <div className="brutal-box-sm p-4 col-span-1">
                                            <div className="flex items-center gap-2 mb-3">
                                                <div className="w-2 h-2 bg-brutal-green" />
                                                <span className="font-bold text-brutal-cream uppercase text-xs">Dhan Connect</span>
                                            </div>
                                            <div className="h-2 bg-brutal-cream/20 mb-2 w-full" />
                                            <div className="h-6 bg-brutal-cream/10 w-full" />
                                        </div>
                                        {/* Trading Status mock */}
                                        <div className="brutal-box-sm p-4 col-span-1">
                                            <div className="flex items-center gap-2 mb-3">
                                                <div className="w-2 h-2 bg-brutal-green animate-pulse" />
                                                <span className="font-bold text-brutal-cream uppercase text-xs">AI Trading</span>
                                            </div>
                                            <div className="flex items-center justify-between">
                                                <span className="font-mono text-xs text-brutal-cream/50">Status</span>
                                                <div className="w-10 h-5 bg-brutal-green border-2 border-brutal-black" />
                                            </div>
                                        </div>
                                    </div>
                                    {/* Portfolio mock */}
                                    <div className="brutal-box-sm p-4">
                                        <div className="flex items-center gap-2 mb-3">
                                            <div className="w-2 h-2 bg-brutal-cream" />
                                            <span className="font-bold text-brutal-cream uppercase text-xs">Portfolio Overview</span>
                                        </div>
                                        <div className="grid grid-cols-3 gap-2">
                                            {['Funds', 'Holdings', 'Positions'].map((l) => (
                                                <div key={l} className="text-center">
                                                    <div className="h-8 bg-brutal-cream/10 mb-1" />
                                                    <span className="font-mono text-[10px] text-brutal-cream/40 uppercase">{l}</span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                    <div className="text-center pt-2">
                                        <span className="font-mono text-xs text-brutal-cream/30 uppercase tracking-widest">
                                            [ Sign in to access live data ]
                                        </span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </section>

                {/* ─── CTA BANNER ─── */}
                {!user && (
                    <section className="border-t-4 border-brutal-white">
                        <div className="max-w-7xl mx-auto px-6 lg:px-8 py-20 text-center space-y-8">
                            <h2 className="text-5xl font-bold text-brutal-cream uppercase tracking-tight">
                                Ready to Let AI Trade For You?
                            </h2>
                            <p className="text-brutal-cream/60 font-mono text-lg max-w-2xl mx-auto">
                                Join now, connect your Dhan account, and watch the multi-agent AI system work every day.
                            </p>
                            <div className="flex flex-col sm:flex-row gap-4 justify-center">
                                <Link
                                    href="/signup"
                                    id="cta-signup-btn"
                                    className="brutal-btn px-10 py-5 text-lg"
                                    aria-label="Create a free account"
                                >
                                    Create Free Account
                                </Link>
                                <Link
                                    href="/login"
                                    id="cta-signin-btn"
                                    className="bg-brutal-black border-4 border-brutal-white text-brutal-cream font-bold py-5 px-10 transition-all transform hover:translate-x-1 hover:translate-y-1 hover:shadow-brutal-sm active:translate-x-2 active:translate-y-2 active:shadow-none shadow-brutal uppercase tracking-wider text-lg"
                                    aria-label="Sign in to existing account"
                                >
                                    Sign In
                                </Link>
                            </div>
                        </div>
                    </section>
                )}
            </main>
        </div>
    )
}
