const PREFIX = `perfil-tienda:${encodeURIComponent(self.registration.scope)}:`;
const CACHE = `${PREFIX}core-v12`;
const DATA_CACHE = `${PREFIX}data-v1`;
const urlFor = path => new URL(path, self.registration.scope).href;
const CORE = ['./','index.html','styles.css','operational.css','app.js','manifest.webmanifest','assets/icon.svg','assets/icon-192.png','assets/icon-512.png'].map(urlFor);
const DATA_URLS = ['data/dashboard.json','data/audit.json'].map(urlFor);
const SNAPSHOT = urlFor('data/.verified-snapshot');
let refreshing;

function validPair(pair) {
  return pair?.dashboard?.schemaVersion === 2 && pair?.audit?.schemaVersion === 2 &&
    pair.audit.issueCount === 0 && typeof pair.dashboard.generatedAt === 'string' &&
    pair.dashboard.generatedAt.length > 0 && pair.dashboard.generatedAt === pair.audit.generatedAt &&
    Array.isArray(pair.dashboard.directory) && pair.dashboard.directory.length > 0 &&
    Array.isArray(pair.dashboard.months) && pair.dashboard.months.length > 0 &&
    Array.isArray(pair.dashboard.graphs) && Array.isArray(pair.dashboard.metricHeaders) &&
    ['profile','business','mix','partners'].every(key => pair.dashboard[key] && typeof pair.dashboard[key] === 'object');
}

async function refreshData() {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 12000);
  try {
    const responses = await Promise.all(DATA_URLS.map(url => fetch(url, {cache:'no-store', signal:controller.signal})));
    if (responses.some(response => !response.ok)) throw new Error('Datos no disponibles');
    const [dashboard,audit] = await Promise.all(responses.map(response => response.json()));
    const pair = {dashboard,audit};
    if (!validPair(pair)) throw new Error('Construcción inconsistente');
    try {
      const cache = await caches.open(DATA_CACHE);
      await cache.put(SNAPSHOT, new Response(JSON.stringify(pair), {headers:{'Content-Type':'application/json'}}));
    } catch (_) { /* Una cuota de caché agotada no impide usar datos válidos de la red. */ }
    return pair;
  } finally { clearTimeout(timeout); }
}

async function serveData(url) {
  let pair, offline = false;
  try {
    if (!refreshing) refreshing = refreshData().finally(() => { refreshing = null; });
    pair = await refreshing;
  } catch (_) {
    try {
      const cached = await (await caches.open(DATA_CACHE)).match(SNAPSHOT);
      pair = cached ? await cached.json() : null;
    } catch (_) { pair = null; }
    if (!validPair(pair)) return new Response('Datos verificados no disponibles', {status:503});
    offline = true;
  }
  return new Response(JSON.stringify(url === DATA_URLS[0] ? pair.dashboard : pair.audit), {
    headers:{'Content-Type':'application/json', 'Cache-Control':'no-store', 'X-Perfil-Offline':offline ? '1' : '0'}
  });
}

self.addEventListener('install', event => event.waitUntil((async () => {
  const cache = await caches.open(CACHE);
  await cache.addAll(CORE.map(url => new Request(url, {cache:'reload'})));
  await refreshData().catch(() => {});
  await self.skipWaiting();
})()));
self.addEventListener('activate', event => event.waitUntil((async () => {
  const keys = await caches.keys();
  await Promise.all(keys.filter(key => key.startsWith(PREFIX) && key !== CACHE && key !== DATA_CACHE).map(key => caches.delete(key)));
  await self.clients.claim();
})()));

async function serveAsset(request) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(request, {cache:'no-store', signal:controller.signal});
    if (!response.ok) throw new Error('Recurso no disponible');
    try { await (await caches.open(CACHE)).put(request, response.clone()); } catch (_) {}
    return response;
  } catch (_) {
    const cache = await caches.open(CACHE);
    const cached = await cache.match(request) || (request.mode === 'navigate' ? await cache.match(urlFor('index.html')) : null);
    return cached || new Response('Recurso no disponible sin conexión', {status:504});
  } finally { clearTimeout(timeout); }
}

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin || !url.href.startsWith(self.registration.scope)) return;
  if (DATA_URLS.includes(url.href)) event.respondWith(serveData(url.href));
  else if (event.request.mode === 'navigate' || CORE.includes(url.href)) event.respondWith(serveAsset(event.request));
});
