const CACHE_NAME = 'crs-fleet-v2'; // Upgraded to force browsers to delete v1
const API_URL = 'https://crsdashboard.onrender.com';

// Merged static files to cache so the app opens without internet
const ASSETS = [
    '/',
    '/portal.html',
    '/index.html',
    '/manifest.json',
    '/icon-192.png',
    '/icon-512.png'
];

// --- 1. INSTALL & CACHE UI ---
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => cache.addAll(ASSETS))
    );
    // Forces the new Service Worker to take over immediately
    self.skipWaiting(); 
});

// --- 2. CLEAN UP OLD CACHES (Deletes your old 'crs-fleet-v1') ---
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys => Promise.all(
            keys.map(key => {
                if (key !== CACHE_NAME) return caches.delete(key);
            })
        ))
    );
    self.clients.claim();
});

// --- 3. INDEXED-DB SETUP (The Offline Vault) ---
const DB_NAME = 'crs-offline-db';
const STORE_NAME = 'post-queue';

function openDB() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, 1);
        request.onupgradeneeded = event => {
            const db = event.target.result;
            if (!db.objectStoreNames.contains(STORE_NAME)) {
                db.createObjectStore(STORE_NAME, { keyPath: 'id', autoIncrement: true });
            }
        };
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

async function saveToQueue(url, method, body) {
    const db = await openDB();
    const tx = db.transaction(STORE_NAME, 'readwrite');
    tx.objectStore(STORE_NAME).add({ url, method, body, timestamp: Date.now() });
    return new Promise(resolve => tx.oncomplete = resolve);
}

// --- 4. THE SYNC ENGINE ---
async function syncQueue() {
    const db = await openDB();
    const tx = db.transaction(STORE_NAME, 'readonly');
    const store = tx.objectStore(STORE_NAME);
    
    const requests = await new Promise(resolve => {
        const req = store.getAll();
        req.onsuccess = () => resolve(req.result);
    });

    if (requests.length === 0) return;

    for (const item of requests) {
        try {
            const res = await fetch(item.url, {
                method: item.method,
                headers: { 'Content-Type': 'application/json' },
                body: item.body
            });
            
            if (res.ok) {
                // Delete from vault if successfully sent to Render
                const delTx = db.transaction(STORE_NAME, 'readwrite');
                delTx.objectStore(STORE_NAME).delete(item.id);
            }
        } catch (err) {
            console.log('Still offline, will retry syncing later.');
            break; // Stop trying the rest of the queue if we are still offline
        }
    }
}

// --- 5. THE TRAFFIC COP (Merged Fetch Logic) ---
self.addEventListener('fetch', event => {
    const req = event.request;
    const url = new URL(req.url);

    // Auto-sync whenever the app attempts any network request
    syncQueue();

    // SCENARIO A: Offline Form Submissions (POST to API)
    if (req.method === 'POST' && url.origin === API_URL) {
        event.respondWith(
            fetch(req.clone()).catch(async () => {
                // If network fails, lock the form data in the offline vault
                const body = await req.clone().text();
                await saveToQueue(req.url, req.method, body);
                
                // Lie to the frontend and say it succeeded so the UI resets
                return new Response(JSON.stringify({ message: "Saved offline. Will sync when connected." }), {
                    headers: { 'Content-Type': 'application/json' },
                    status: 200
                });
            })
        );
        return;
    }

    // SCENARIO B: Loading App Files and Data (GET requests)
    if (req.method === 'GET') {
        event.respondWith(
            fetch(req)
                .then(res => {
                    // Network success! Save a fresh copy to the cache
                    const resClone = res.clone();
                    caches.open(CACHE_NAME).then(cache => cache.put(req, resClone));
                    return res;
                })
                .catch(() => {
                    // Network failed (offline). Serve the files/data from the cache!
                    return caches.match(req);
                })
        );
    }
});
