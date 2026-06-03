/*
 * 아트인캘린더 서비스워커
 * 전략: 핵심 파일은 network-first(온라인이면 항상 최신 배포본을 받음 → 자동 업데이트),
 *       오프라인일 때만 캐시 폴백. 새 버전 배포 시 캐시를 자동 교체한다.
 */
const VERSION = "1.0.0"; // version.js와 함께 올린다 (배포 워크플로가 자동 치환)
const CACHE = "aic-" + VERSION;

const ASSETS = [
  "./",
  "./index.html",
  "./styles.css",
  "./app.js",
  "./version.js",
  "./manifest.webmanifest",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/apple-touch-icon.png",
  "./icons/favicon.ico",
];

self.addEventListener("install", (e) => {
  self.skipWaiting();
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(ASSETS).catch(() => {}))
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  // Firebase 등 외부 도메인은 서비스워커가 건드리지 않음 (실시간 동기화 보호)
  if (url.origin !== self.location.origin) return;

  // 네트워크 우선 → 성공하면 캐시에 갱신, 실패하면 캐시로 폴백
  e.respondWith(
    fetch(req)
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
        return res;
      })
      .catch(() => caches.match(req).then((r) => r || caches.match("./index.html")))
  );
});
