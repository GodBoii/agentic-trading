import Link from 'next/link'

export default function NotFound() {
    return (
        <div className="min-h-screen bg-brutal-black flex items-center justify-center p-6">
            <div className="brutal-box p-12 text-center max-w-md w-full animate-pop">
                <h1 className="text-9xl font-bold text-brutal-cream font-mono mb-4">404</h1>
                <h2 className="text-2xl font-bold text-brutal-cream uppercase tracking-tight mb-6">Page Not Found</h2>
                <p className="text-brutal-cream/70 font-mono mb-8">
                    The page you are looking for does not exist or has been moved.
                </p>
                <Link
                    href="/dashboard"
                    className="brutal-btn block w-full py-4 text-center font-bold no-underline hover:no-underline"
                >
                    Return Home
                </Link>
            </div>
        </div>
    )
}
