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

  /* Startbildschirm: Wechseltext (data-wechseltext = id eines json_script mit der Textliste).
     Der erste Text steht schon im Markup (Tageszeit-Gruß); alle 6 s blendet der nächste ein.
     Mit prefers-reduced-motion wechselt der Text ohne Überblendung. Kein aria-live: ein
     Screenreader soll nicht alle 6 s unterbrochen werden, er liest den ersten Gruß. */
  var WECHSEL_TAKT = 6000;
  var WECHSEL_BLENDE = 400;
  var LANG_AB = 28; // Zeichen: längere Texte werden kleiner gesetzt

  function wechselText(h1) {
    var quelle = document.getElementById(h1.getAttribute("data-wechseltext"));
    var texte = [];
    try {
      texte = JSON.parse(quelle ? quelle.textContent : "[]");
    } catch (e) {
      texte = [];
    }
    if (!Array.isArray(texte) || texte.length < 2) {
      return;
    }
    var ruhig = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var i = 0;

    function setzen(text) {
      h1.textContent = text;
      h1.classList.toggle("ist-lang", text.length > LANG_AB);
    }

    window.setInterval(function () {
      if (document.hidden) {
        return;
      }
      i = (i + 1) % texte.length;
      var naechster = String(texte[i]);
      if (ruhig) {
        setzen(naechster);
        return;
      }
      h1.classList.add("ist-ausgeblendet");
      window.setTimeout(function () {
        setzen(naechster);
        h1.classList.remove("ist-ausgeblendet");
      }, WECHSEL_BLENDE);
    }, WECHSEL_TAKT);
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-wechseltext]").forEach(function (h1) {
      h1.setAttribute("aria-live", "off");
      wechselText(h1);
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
