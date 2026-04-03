const CACHE_NAME = 'fleet-pwa-v1';
const urlsToCache = [
    '/driver.html',
    '/manifest.json'
];

// Install the Service Worker and save files to the phone's cache
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
        .then(cache => {
            return cache.addAll(urlsToCache);
        })
    );
});

// Intercept network requests and serve from cache if offline
self.addEventListener('fetch', event => {
    event.respondWith(
        caches.match(event.request)
        .then(response => {
            // Return cached version if found, otherwise go to network
            if (response) {
                return response;
            }
            return fetch(event.request);
        })
    );
});
