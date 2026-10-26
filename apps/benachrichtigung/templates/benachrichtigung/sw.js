/* Nestwerk Service Worker (AP08). Scope "/", ausgeliefert ohne Cache.
   Aufgaben: Push anzeigen (klassisch, auch für das Declarative-Format), Klick -> Deep-Link,
   App-Badge, schlichte Offline-Seite. Kein weiteres Caching. */
"use strict";

var VERSION = "nestwerk-sw-1";
var OFFLINE_URL = "{{ offline_url|escapejs }}";
var ICON_URL = "{{ icon_url|escapejs }}";
var BADGE_URL = "{{ badge_url|escapejs }}";
var START_URL = "{{ start_url|escapejs }}";

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(VERSION).then(function (cache) {
      return cache.add(new Request(OFFLINE_URL, { cache: "reload" }));
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (namen) {
      return Promise.all(namen.filter(function (n) { return n !== VERSION; })
        .map(function (n) { return caches.delete(n); }));
    }).then(function () { return self.clients.claim(); })
  );
});

// Nur Seitenaufrufe: bei fehlender Verbindung die Offline-Seite zeigen.
self.addEventListener("fetch", function (event) {
  if (event.request.mode !== "navigate") { return; }
  event.respondWith(
    fetch(event.request).catch(function () {
      return caches.match(OFFLINE_URL).then(function (treffer) {
        return treffer || Response.error();
      });
    })
  );
});

function badgeSetzen(anzahl) {
  if (typeof anzahl !== "number" || !isFinite(anzahl)) { return Promise.resolve(); }
  var nav = self.navigator;
  if (anzahl > 0 && nav && nav.setAppBadge) { return nav.setAppBadge(anzahl).catch(function () {}); }
  if (nav && nav.clearAppBadge) { return nav.clearAppBadge().catch(function () {}); }
  return Promise.resolve();
}

// Declarative Web Push ({"web_push": 8030, "notification": {...}}) und schlichtes JSON {title, body, navigate}.
function nachrichtLesen(daten) {
  var n = null;
  if (daten && daten.web_push === 8030 && daten.notification) { n = daten.notification; }
  else if (daten && daten.title) { n = daten; }
  if (!n) { return { title: "Nestwerk", body: "", navigate: START_URL, badge: null }; }
  var badge = n.app_badge !== undefined ? n.app_badge : daten.app_badge;
  return {
    title: n.title || "Nestwerk",
    body: n.body || "",
    navigate: n.navigate || START_URL,
    badge: badge === undefined || badge === null ? null : Number(badge)
  };
}

self.addEventListener("push", function (event) {
  var daten = null;
  try { daten = event.data ? event.data.json() : null; } catch (e) { daten = null; }
  var m = nachrichtLesen(daten);
  event.waitUntil(Promise.all([
    self.registration.showNotification(m.title, {
      body: m.body,
      icon: ICON_URL,
      badge: BADGE_URL,
      tag: m.navigate,
      data: { navigate: m.navigate }
    }),
    badgeSetzen(m.badge)
  ]));
});

// Tippen auf die Meldung: vorhandenes Fenster fokussieren und zum Ziel navigieren, sonst öffnen.
self.addEventListener("notificationclick", function (event) {
  event.notification.close();
  var ziel = (event.notification.data && event.notification.data.navigate) || START_URL;
  var url = new URL(ziel, self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (fenster) {
      for (var i = 0; i < fenster.length; i++) {
        var f = fenster[i];
        if (new URL(f.url).origin === self.location.origin && "focus" in f) {
          return f.focus().then(function (fokus) {
            return "navigate" in fokus ? fokus.navigate(url) : self.clients.openWindow(url);
          });
        }
      }
      return self.clients.openWindow(url);
    })
  );
});
