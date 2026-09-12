import type { MetadataRoute } from 'next'

export default function manifest(): MetadataRoute.Manifest {
    return {
        id: '/', name: 'PolyCognition', short_name: 'PolyCognition',
        description: 'Portfolio, live AI agent runs and trade history.',
        start_url: '/dashboard', scope: '/', display: 'standalone',
        background_color: '#0C0B0A', theme_color: '#0C0B0A',
        icons: [
            { src: '/icons/app-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
            { src: '/icons/app-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
            { src: '/icons/maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
    }
}
