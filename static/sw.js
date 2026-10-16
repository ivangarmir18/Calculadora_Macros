/* Service worker: la app abre al instante y arranca aunque el servidor esté un momento caído.
   Estrategia: red primero, caché como respaldo. Los datos (/api) nunca se cachean, para no mostrar cifras viejas. */
const CACHE = "macros-v4";
const SHELL = ["/", "/static/style.css", "/static/icons.js", "/static/charts.js", "/static/app.js", "/static/icons/icon.svg"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin || u.pathname.startsWith("/api/")) return;
  e.respondWith(
    fetch(e.request).then((res) => {
      if (res.ok && (u.pathname === "/" || u.pathname.startsWith("/static/") || u.pathname.startsWith("/uploads/"))) {
        const copy = res.clone(); caches.open(CACHE).then((c) => c.put(e.request, copy));
      }
      return res;
    }).catch(() => caches.match(e.request))
  );
});

