// Service worker minimale di Fidelitree.
// Scopo: rendere l'app installabile. NON mette in cache pagine o API autenticate
// (dati personali): solo la "shell" statica (icone, manifest), con rete per prima.
const CACHE = "fidelitree-shell-v2";
const SHELL = ["/static/manifest.webmanifest", "/static/icon-192.png", "/static/apple-touch-icon.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);
  // Solo GET della shell statica same-origin; tutto il resto (pagine, /api, cookie) va in rete.
  if (req.method !== "GET" || url.origin !== self.location.origin || !SHELL.includes(url.pathname)) {
    return;
  }
  // network-first: se la rete manca si ripiega sulla copia in cache
  event.respondWith(
    fetch(req)
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((cache) => cache.put(req, copy));
        return res;
      })
      .catch(() => caches.match(req))
  );
});
