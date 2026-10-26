/* Nestwerk Marken-Look: Darstellung (hell/dunkel/System) und Splash nur einmal je Sitzung.
   Der Modus steckt im Cookie nestwerk_marke_modus (Server setzt data-modus beim Rendern),
   "system" = Attribut entfernen, dann gilt prefers-color-scheme. */
(function () {
  "use strict";

  var COOKIE = "nestwerk_marke_modus";
  var GUELTIG = ["hell", "dunkel", "system"];

  function modusSetzen(modus) {
    if (GUELTIG.indexOf(modus) === -1) {
      return;
    }
    if (modus === "system") {
      document.body.removeAttribute("data-modus");
    } else {
      document.body.setAttribute("data-modus", modus);
    }
    document.cookie = COOKIE + "=" + modus + "; path=/; max-age=31536000; SameSite=Lax";
  }

  function aktuellerModus() {
    return document.body.getAttribute("data-modus") || "system";
  }

  document.addEventListener("change", function (e) {
    var ziel = e.target;
    if (ziel && ziel.matches && ziel.matches("[data-modus-wahl]")) {
      modusSetzen(ziel.value);
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    var aktuell = aktuellerModus();
    document.querySelectorAll("[data-modus-wahl]").forEach(function (eingabe) {
      eingabe.checked = eingabe.value === aktuell;
    });

    var splash = document.querySelector("[data-splash]");
    if (!splash) {
      return;
    }
    try {
      if (window.sessionStorage.getItem("nw-splash")) {
        splash.remove();
      } else {
        window.sessionStorage.setItem("nw-splash", "1");
      }
    } catch (fehler) {
      /* Speicher gesperrt: Splash läuft einfach jedes Mal. */
    }
  });
})();
