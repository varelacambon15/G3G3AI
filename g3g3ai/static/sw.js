// Service worker mínimo: permite instalar G3G3AI como app (PWA). No cachea la API.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {});
