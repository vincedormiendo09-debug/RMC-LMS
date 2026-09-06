/* =====================================================
   REGIS MARIE COLLEGE - PUSH REGISTRATION SERVICE
   Registers devices, requests permissions, & links to Supabase
===================================================== */

// Replace with your VAPID Public Key string
const VAPID_PUBLIC_KEY = 'PASTE_YOUR_VAPID_PUBLIC_KEY_HERE';

async function registerDeviceForMobileAlerts(currentUserId, supabaseClient) {
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    console.info('⚠️ Web push notifications are not supported on this browser/environment.');
    return;
  }

  if (!currentUserId || !supabaseClient) {
    console.warn('Cannot register push alerts: Missing user session or database client.');
    return;
  }

  try {
    // 1. Register Service Worker with root scope
    await navigator.serviceWorker.register('/static/sw.js', { scope: '/' });
    const registration = await navigator.serviceWorker.ready;

    // 2. Request Notification Permission
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') {
      console.warn('⚠️ Push notification permission was not granted by user.');
      return;
    }

    if (!VAPID_PUBLIC_KEY || VAPID_PUBLIC_KEY.includes('PASTE_YOUR')) {
      console.error('❌ VAPID_PUBLIC_KEY is not configured in push-register.js.');
      return;
    }

    const convertedVapidKey = urlBase64ToUint8Array(VAPID_PUBLIC_KEY);

    // 3. Obtain or Refresh Push Subscription
    let subscription = await registration.pushManager.getSubscription();

    if (!subscription) {
      try {
        subscription = await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: convertedVapidKey
        });
      } catch (subErr) {
        console.warn('Could not subscribe with current credentials. Retrying renewal...', subErr);
        const existing = await registration.pushManager.getSubscription();
        if (existing) await existing.unsubscribe();

        subscription = await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: convertedVapidKey
        });
      }
    }

    const subJson = subscription.toJSON();
    const endpoint = subJson.endpoint;
    const p256dh = subJson.keys?.p256dh;
    const auth = subJson.keys?.auth;

    if (!endpoint || !p256dh || !auth) {
      console.error('❌ Push subscription generated incomplete key pairs.');
      return;
    }

    // 4. Save/Update Device Registration in Supabase
    const { error } = await supabaseClient
      .from('push_subscriptions')
      .upsert(
        [
          {
            user_id: String(currentUserId).trim(),
            endpoint: endpoint,
            p256dh: p256dh,
            auth: auth
          }
        ],
        { onConflict: 'endpoint' }
      );

    if (error) {
      console.error('❌ Supabase push registration sync failed:', error.message);
    } else {
      console.log('📱 Device successfully linked for lock-screen push alerts.');
    }
  } catch (err) {
    console.error('⚠️ Push registration error:', err);
  }
}

function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding)
    .replace(/\-/g, '+')
    .replace(/_/g, '/');

  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);

  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}