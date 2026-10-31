// Service worker de GPV Product TimeFlow. Estrategia conservadora:
// - Recursos estáticos (css, js, fuentes, imágenes): cache-first.
// - Navegación y datos: siempre red (nunca se almacenan expedientes, PDF ni exportaciones).
const CACHE = "timeflow-static-v4.0.0";
const STATIC = ["/css/app.css", "/js/app.js", "/js/theme-init.js", "/img/icon.svg", "/fonts/Inter-Regular.woff2", "/fonts/Inter-SemiBold.woff2"];
self.addEventListener("install", e => e.waitUntil(caches.open(CACHE).then(c => c.addAll(STATIC)).then(() => self.skipWaiting())));
self.addEventListener("activate", e => e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (/^\/(css|js|fonts|img)\//.test(url.pathname)) {
    e.respondWith(caches.match(e.request).then(hit => hit || fetch(e.request).then(res => { const copy = res.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)); return res; })));
  }
});
