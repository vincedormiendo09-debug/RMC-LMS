/* =====================================================
   REGIS MARIE COLLEGE - MOBILE BACKGROUND SERVICE WORKER
   Lock-screen banners, vibration, badge counts, & routing
===================================================== */

// Immediate activation on installation
self.addEventListener('install', function (event) {
  self.skipWaiting();
});

self.addEventListener('activate', function (event) {
  event.waitUntil(clients.claim());
});

// 1. Listen for Incoming Web Push Messages
self.addEventListener('push', function (event) {
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
    icon: "/static/icons/icon-192.png",       // App logo in notification
    badge: "/static/icons/badge-72.png",      // Monochrome icon in mobile status bar
    vibrate: [150, 75, 150, 75, 200],         // Haptic alert pattern
    data: {
      url: targetUrl,
      activityId: payload.activityId || null
    },
    tag: payload.tag || `activity-${payload.activityId || Date.now()}`,
    renotify: true,
    requireInteraction: false                 // Shows on lock screen and drops down banner
  };

  // Update App Icon Badge on Mobile Home Screen (if supported)
  if (navigator.setAppBadge) {
    navigator.setAppBadge(payload.unreadCount || 1).catch(() => {});
  }

  // Display Lock Screen Alert, Status Bar Icon, and Drop-Down Banner
  event.waitUntil(
    self.registration.showNotification(title, options)
  );
});

// 2. Handle Student Tapping the Mobile Notification
self.addEventListener('notificationclick', function (event) {
  event.notification.close();

  // Clear app badge when notification is opened
  if (navigator.clearAppBadge) {
    navigator.clearAppBadge().catch(() => {});
  }

  if (event.action === 'dismiss') {
    return;
  }

  const targetUrl = event.notification.data?.url || "/dashboard.html";

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (clientList) {
      // Focus existing tab if already open
      for (const client of clientList) {
        if (client.url.includes(targetUrl) && 'focus' in client) {
          return client.focus();
        }
      }
      // Otherwise open a new portal window
      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
      }
    })
  );
});