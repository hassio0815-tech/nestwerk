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

  /* Startbildschirm: Begrüßung wechselt alle paar Sekunden die Sprache (data-gruss-<code>).
     Nur der Text wechselt, die Seitensprache bleibt; Screenreader lesen den ersten Gruß. */
  var GRUSS_TAKT = 4000;

  function grussWechsel(h1) {
    var texte = [];
    Array.prototype.forEach.call(h1.attributes, function (a) {
      if (a.name.indexOf("data-gruss-") === 0 && a.name !== "data-gruss-wechsel") {
        texte.push({ code: a.name.slice(11), text: a.value });
      }
    });
    if (texte.length < 2) {
      return;
    }
    var ruhig = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var i = 0;
    window.setInterval(function () {
      i = (i + 1) % texte.length;
      var naechster = texte[i];
      if (ruhig) {
        h1.textContent = naechster.text;
        h1.setAttribute("lang", naechster.code);
        return;
      }
      h1.classList.add("ist-ausgeblendet");
      window.setTimeout(function () {
        h1.textContent = naechster.text;
        h1.setAttribute("lang", naechster.code);
        h1.classList.remove("ist-ausgeblendet");
      }, 400);
    }, GRUSS_TAKT);
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-gruss-wechsel]").forEach(function (h1) {
      h1.setAttribute("aria-live", "off");
      grussWechsel(h1);
    });

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
