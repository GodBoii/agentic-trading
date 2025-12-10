'use client'

import { useEffect } from 'react'

export default function Error({
    error,
    reset,
}: {
    error: Error & { digest?: string }
    reset: () => void
}) {
    useEffect(() => {
        // Log the error to an error reporting service
        console.error(error)
    }, [error])

    return (
        <div className="min-h-screen bg-brutal-black flex items-center justify-center p-6">
            <div className="brutal-box p-10 text-center max-w-md w-full animate-shake">
                <div className="inline-flex items-center justify-center w-20 h-20 bg-brutal-red border-4 border-brutal-black mb-6">
                    <svg className="w-10 h-10 text-brutal-black" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={3}>
                        <path strokeLinecap="square" strokeLinejoin="miter" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                </div>
                <h2 className="text-3xl font-bold text-brutal-cream uppercase tracking-tight mb-4">
                    Something went wrong!
                </h2>
                <p className="text-brutal-red font-mono text-sm mb-8 p-4 border-2 border-brutal-red bg-brutal-red/10">
                    {error.message || "An unexpected error occurred."}
                </p>
                <div className="flex gap-4 flex-col sm:flex-row">
                    <button
                        onClick={() => reset()}
                        className="brutal-btn w-full py-3"
                    >
                        Try again
                    </button>
                    <a href="/" className="brutal-btn w-full py-3 bg-brutal-black text-brutal-cream border-brutal-white hover:bg-brutal-gray-900 text-center block">
                        Go Home
                    </a>
                </div>
            </div>
        </div>
    )
}
