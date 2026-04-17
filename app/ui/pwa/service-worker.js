const CACHE_NAME = "fitclaw-aiops-shell-v33";
const APP_SHELL = [
  "/app-manifest.webmanifest",
  "/app-assets/chat-app.css",
  "/app-assets/chat-app.js",
  "/app-assets/finance.css",
  "/app-assets/finance.js",
  "/app-assets/memorycore-page.css",
  "/app-assets/memorycore-page.js",
  "/app-assets/whatsapp-beta.css",
  "/app-assets/whatsapp-beta.js",
  "/app-assets/transit-live.css",
  "/app-assets/transit-live.js",
  "/app-assets/landing.css",
  "/app-assets/landing.js",
  "/app-assets/icons/icon-192.png",
  "/app-assets/icons/icon-512.png",
  "/app-assets/icons/apple-touch-icon.png",
];

const NAV_ROUTES = ["/", "/app", "/finance", "/memorycore", "/transit-live", "/whatsapp-beta"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  const isNavigation = request.mode === "navigate" || request.destination === "document";

  // Network-first for all PWA navigation routes; fall back to cache then /app
  if (isNavigation && NAV_ROUTES.includes(url.pathname)) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response && response.status === 200 && response.type !== "opaque") {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          }
          return response;
        })
        .catch(async () => {
          const cached = await caches.match(request);
          if (cached) return cached;
          return caches.match("/app");
        })
    );
    return;
  }

  // Network-only for API calls, with silent fallback
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(fetch(request).catch(() => caches.match("/app")));
    return;
  }

  // Network-first for app assets so normal refreshes pick up UI fixes promptly.
  if (url.pathname.startsWith("/app-assets/") || url.pathname === "/app-manifest.webmanifest") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (!response || response.status !== 200 || response.type === "opaque") {
            return response;
          }
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          return response;
        })
        .catch(async () => {
          const cached = await caches.match(request);
          if (cached) return cached;
          return caches.match("/app");
        })
    );
    return;
  }

  // Cache-first for everything else.
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request)
        .then((response) => {
          if (!response || response.status !== 200 || response.type === "opaque") {
            return response;
          }
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          return response;
        })
        .catch(() => caches.match("/app"));
    })
  );
});
