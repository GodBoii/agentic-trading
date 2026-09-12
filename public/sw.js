/* Only the public offline screen is cached. Account pages and APIs always use the network. */
const CACHE = 'polycognition-offline-v1'
self.addEventListener('install', (event) => {
    event.waitUntil(caches.open(CACHE).then((cache) => cache.add('/offline.html')))
})
self.addEventListener('activate', (event) => {
    event.waitUntil(caches.keys().then((keys) => Promise.all(keys
        .filter((key) => key.startsWith('polycognition-offline-') && key !== CACHE)
        .map((key) => caches.delete(key)))).then(() => self.clients.claim()))
})
self.addEventListener('message', (event) => {
    if (event.data?.type === 'ACTIVATE_UPDATE') self.skipWaiting()
})
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url)
    if (event.request.method !== 'GET' || url.origin !== self.location.origin || event.request.mode !== 'navigate') return
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/auth/')) return
    event.respondWith(fetch(event.request).catch(async () =>
        (await caches.match('/offline.html')) || new Response('You are offline. Reconnect to view your portfolio.', {
            status: 503, headers: { 'Content-Type': 'text/plain' },
        })))
})
