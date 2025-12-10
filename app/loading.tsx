export default function Loading() {
    return (
        <div className="min-h-screen bg-brutal-black flex items-center justify-center p-8">
            <div className="flex flex-col items-center">
                {/* Brutal Spinner */}
                <div className="relative w-24 h-24 mb-8">
                    <div className="absolute inset-0 border-8 border-brutal-gray-800"></div>
                    <div className="absolute inset-0 border-8 border-brutal-green border-t-transparent animate-spin"></div>
                </div>

                {/* Loading Text */}
                <div className="brutal-box-sm border-brutal-cream/50 shadow-none px-6 py-3 bg-brutal-black animate-pulse">
                    <p className="text-brutal-cream font-mono text-xl font-bold uppercase tracking-wider">
                        Loading...
                    </p>
                </div>
            </div>
        </div>
    )
}
