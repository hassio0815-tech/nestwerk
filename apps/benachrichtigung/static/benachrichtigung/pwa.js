/* Nestwerk PWA (AP08): Service Worker registrieren, Badge zurücksetzen, Push-Karte steuern.
   Die Berechtigungsabfrage kommt nur aus dem Klick auf "Benachrichtigungen aktivieren". */
(function () {
  "use strict";

  var istIos = /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  var standalone = (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches) ||
    navigator.standalone === true;

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function () {});
    });
  }
  if (navigator.clearAppBadge) {
    navigator.clearAppBadge().catch(function () {});
  }

  function schluesselZuBytes(text) {
    var fuell = "=".repeat((4 - (text.length % 4)) % 4);
    var roh = atob((text + fuell).replace(/-/g, "+").replace(/_/g, "/"));
    var bytes = new Uint8Array(roh.length);
    for (var i = 0; i < roh.length; i++) { bytes[i] = roh.charCodeAt(i); }
    return bytes;
  }

  function anzeigen(karte, name) {
    karte.querySelectorAll("[data-push-zustand]").forEach(function (el) {
      el.hidden = el.getAttribute("data-push-zustand") !== name;
    });
  }

  function fehler(karte, text) {
    var el = karte.querySelector("[data-push-fehler]");
    if (el) { el.textContent = text || ""; el.hidden = !text; }
  }

  function senden(karte, url, daten) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": karte.getAttribute("data-push-csrf") },
      body: JSON.stringify(daten)
    }).then(function (antwort) {
      if (!antwort.ok) { throw new Error("Server " + antwort.status); }
      return antwort.json();
    });
  }

  function anmelden(karte, sub) {
    var daten = sub.toJSON();
    daten.bezeichnung = karte.getAttribute("data-push-bezeichnung") || "";
    return senden(karte, karte.getAttribute("data-push-abo-url"), daten);
  }

  function pruefen(karte) {
    if (!karte.getAttribute("data-push-schluessel")) { return anzeigen(karte, "kein-schluessel"); }
    if (istIos && !standalone) { return anzeigen(karte, "ios-installieren"); }
    if (!("serviceWorker" in navigator && "PushManager" in window && "Notification" in window)) {
      return anzeigen(karte, "nicht-unterstuetzt");
    }
    if (Notification.permission === "denied") { return anzeigen(karte, "blockiert"); }
    navigator.serviceWorker.ready.then(function (reg) {
      return reg.pushManager.getSubscription();
    }).then(function (sub) {
      if (sub && Notification.permission === "granted") {
        anzeigen(karte, "aktiv");
        anmelden(karte, sub).catch(function () {}); // Abgleich mit dem Server beim App-Start
      } else {
        anzeigen(karte, "bereit");
      }
    }).catch(function () { anzeigen(karte, "nicht-unterstuetzt"); });
  }

  function aktivieren(karte) {
    fehler(karte, "");
    // Direkt im Klick-Handler: nur so erlaubt iOS die Abfrage.
    Notification.requestPermission().then(function (erlaubnis) {
      if (erlaubnis !== "granted") { return pruefen(karte); }
      var schluessel = schluesselZuBytes(karte.getAttribute("data-push-schluessel"));
      return navigator.serviceWorker.ready.then(function (reg) {
        var optionen = { userVisibleOnly: true, applicationServerKey: schluessel };
        return reg.pushManager.subscribe(optionen).catch(function () {
          // Altes Abo mit anderem Schlüssel: entfernen und neu abonnieren.
          return reg.pushManager.getSubscription().then(function (alt) {
            return (alt ? alt.unsubscribe() : Promise.resolve()).then(function () {
              return reg.pushManager.subscribe(optionen);
            });
          });
        });
      }).then(function (sub) {
        return anmelden(karte, sub).then(function () { anzeigen(karte, "aktiv"); }, function (e) {
          sub.unsubscribe();
          throw e;
        });
      });
    }).catch(function () {
      fehler(karte, karte.getAttribute("data-push-text-aktivieren-fehler"));
      pruefen(karte);
    });
  }

  function abmelden(karte) {
    fehler(karte, "");
    navigator.serviceWorker.ready.then(function (reg) {
      return reg.pushManager.getSubscription();
    }).then(function (sub) {
      if (!sub) { return null; }
      var endpoint = sub.endpoint;
      return sub.unsubscribe().then(function () {
        return senden(karte, karte.getAttribute("data-push-abmelden-url"), { endpoint: endpoint });
      });
    }).then(function () { anzeigen(karte, "bereit"); }).catch(function () {
      fehler(karte, karte.getAttribute("data-push-text-abmelden-fehler"));
    });
  }

  function alleStarten() {
    document.querySelectorAll("[data-push]").forEach(pruefen);
  }

  document.addEventListener("click", function (ereignis) {
    var knopf = ereignis.target.closest("[data-push-aktion]");
    var karte = knopf && knopf.closest("[data-push]");
    if (!karte) { return; }
    if (knopf.getAttribute("data-push-aktion") === "aktivieren") { aktivieren(karte); }
    else { abmelden(karte); }
  });

  document.addEventListener("DOMContentLoaded", alleStarten);
  document.addEventListener("htmx:afterSettle", alleStarten);
})();
