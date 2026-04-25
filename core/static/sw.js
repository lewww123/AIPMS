self.addEventListener("fetch", function(event) {
  event.respondWith(fetch(event.request));
});

self.addEventListener("install", function(event) {
    self.skipWaiting();
});

self.addEventListener("activate", function(event) {
    event.waitUntil(clients.claim());
});