/* =====================================================
   REGIS MARIE COLLEGE - MOBILE BACKGROUND SERVICE WORKER
   PWA Installation, Caching, Web Push Alerts & Routing
===================================================== */

const CACHE_NAME = 'rmc-lms-cache-v1';
const PRECACHE_ASSETS = [
  '/static/rmc.png',
  '/static/manifest.json',
  '/login.html'
];

// 1. Install: Pre-cache essential assets & activate immediately
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(PRECACHE_ASSETS).catch((err) => {
        console.warn('Pre-caching asset warning:', err);
      });
    })
  );
  self.skipWaiting();
});

// 2. Activate: Clear old caches and claim open pages immediately
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      );
    }).then(() => clients.claim())
  );
});

// 3. Fetch: Required by Chrome/Edge/Android to satisfy PWA install criteria
self.addEventListener('fetch', (event) => {
  // Only handle standard GET requests (bypass POST routes like /register, /login, /api/*)
  if (event.request.method !== 'GET' || !event.request.url.startsWith('http')) {
    return;
  }

  event.respondWith(
    fetch(event.request).catch(() => {
      // Offline fallback: serve cached match if network fails
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
      body: event.data.text() || "New coursework has been posted in your class.",
      url: "/dashboard.html",
      unreadCount: 1
    };
  }

  const title = payload.title || "Regis Marie College Alert";
  const targetUrl = payload.url || "/dashboard.html";

  const options = {
    body: payload.body || "New coursework has been posted in your class.",
    icon: "/static/rmc.png",            // Verified existing school logo
    badge: "/static/rmc.png",           // Mobile status-bar icon
    vibrate: [150, 75, 150, 75, 200],
    data: {
      url: targetUrl,
      activityId: payload.activityId || null
    },
    tag: payload.tag || `activity-${payload.activityId || Date.now()}`,
    renotify: true,
    requireInteraction: false
  };

  // Update app icon badge on mobile home screens (Android / PWA)
  if (navigator.setAppBadge) {
    navigator.setAppBadge(payload.unreadCount || 1).catch(() => {});
  }

  event.waitUntil(
    self.registration.showNotification(title, options)
  );
});

// 5. Notification Click & Tab Focus Handler
self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  if (navigator.clearAppBadge) {
    navigator.clearAppBadge().catch(() => {});
  }

  if (event.action === 'dismiss') {
    return;
  }

  const relativeUrl = event.notification.data?.url || "/dashboard.html";
  const absoluteTarget = new URL(relativeUrl, self.location.origin).href;

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      // Focus tab if user already has this view open
      for (const client of clientList) {
        if (client.url === absoluteTarget && 'focus' in client) {
          return client.focus();
        }
      }
      // Otherwise open a new window straight to the target
      if (clients.openWindow) {
        return clients.openWindow(absoluteTarget);
      }
    })
  );
});