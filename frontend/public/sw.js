// Minimal service worker: exists only so Chrome treats the app as an
// installable PWA. No fetch handling/caching on purpose — the library,
// jobs, and log stream are live data from the backend and must never be
// served stale.
self.addEventListener('install', () => {
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim())
})
