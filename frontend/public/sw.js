// Minimal service worker — enables "Add to Home Screen" on iOS
self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', e => e.waitUntil(clients.claim()))
// No caching — always fetch fresh from network (data dashboard, not offline-first)
self.addEventListener('fetch', e => e.respondWith(fetch(e.request)))
