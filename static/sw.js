/* =====================================================
   REGIS MARIE COLLEGE - MOBILE BACKGROUND SERVICE WORKER
   PWA Installation, Cache Busting, Web Push & Smart Routing
===================================================== */

// Bumped cache version to force-clear any stale HTML cached on user devices
const CACHE_NAME = 'rmc-lms-cache-v3';

// Only precache static, immutable assets — NEVER precache dynamic HTML/Flask templates
const PRECACHE_ASSETS = [
  '/static/rmc.png',
  '/static/manifest.json'
];

// 1. Install: Pre-cache core branding & activate immediately
self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(PRECACHE_ASSETS).catch((err) => {
        console.warn('Pre-caching asset warning:', err);
      });
    })
  );
});

// 2. Activate: Wipe out all older caches (v1, v2) and claim open tabs immediately
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      );
    }).then(() => self.clients.claim())
  );
});

// 3. Fetch: Network-First for HTML/Navigation; Cache fallback only when offline
self.addEventListener('fetch', (event) => {
  // Ignore non-GET and non-HTTP requests
  if (event.request.method !== 'GET' || !event.request.url.startsWith('http')) {
    return;
  }

  const isHtmlRequest = event.request.mode === 'navigate' || 
                        event.request.headers.get('accept')?.includes('text/html');

  if (isHtmlRequest) {
    // ALWAYS fetch HTML fresh from the server so template updates are instant
    event.respondWith(
      fetch(event.request)
        .then((networkResponse) => {
          return networkResponse;
        })
        .catch(() => {
          // Fallback to cache only when completely offline
          return caches.match(event.request);
        })
    );
    return;
  }

  // Static Assets (Images, Manifest, CSS): Try network, fallback to cache
  event.respondWith(
    fetch(event.request)
      .then((networkResponse) => {
        if (networkResponse.status === 200 && event.request.url.includes('/static/')) {
          const clone = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return networkResponse;
      })
      .catch(() => {
        return caches.match(event.request);
      })
  );
});

// 4. Web Push Notification Handler
self.addEventListener('push', (event) => {
  if (!event.data) return;

  let payload = {};
  try {
    payload = event.data.json();
  } catch (err) {
    payload = {
      title: "Regis Marie College Alert",
      body: event.data.text() || "New academic notification received.",
      url: "/notify.html",
      unreadCount: 1
    };
  }

  const title = payload.title || "Regis Marie College Alert";
  const targetUrl = payload.url || "/notify.html";

  const options = {
    body: payload.body || "New coursework or message in your portal.",
    icon: "/static/rmc.png",
    badge: "/static/rmc.png",
    vibrate: [150, 75, 150, 75, 200],
    data: {
      url: targetUrl,
      activityId: payload.activityId || null
    },
    tag: payload.tag || `notif-${Date.now()}`,
    renotify: true,
    requireInteraction: false
  };

  // Update badge counter on supported Android / PWA app icons
  if (navigator.setAppBadge) {
    navigator.setAppBadge(payload.unreadCount || 1).catch(() => {});
  }

  event.waitUntil(
    self.registration.showNotification(title, options)
  );
});

// 5. Notification Click & Smart Window Re-use
self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  if (navigator.clearAppBadge) {
    navigator.clearAppBadge().catch(() => {});
  }

  if (event.action === 'dismiss') {
    return;
  }

  const relativeUrl = event.notification.data?.url || "/notify.html";
  const absoluteTarget = new URL(relativeUrl, self.location.origin).href;

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      // 1. If an open tab is already on this exact target URL, simply focus it
      for (const client of clientList) {
        if (client.url === absoluteTarget && 'focus' in client) {
          return client.focus();
        }
      }

      // 2. If the user already has any portal page open, navigate that window instead of opening a duplicate tab
      for (const client of clientList) {
        if ('navigate' in client && 'focus' in client) {
          return client.navigate(absoluteTarget).then((c) => c ? c.focus() : null);
        }
      }

      // 3. Otherwise open a new window
      if (self.clients.openWindow) {
        return self.clients.openWindow(absoluteTarget);
      }
    })
  );
});