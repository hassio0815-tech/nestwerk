/* Nestwerk Spiel-Ebene: Fortschritt füllen, Punkte zählen und fliegen, Aufgabe geschafft.
   Rang-Aufstieg, Mod-Enthüllung, Flamme und Federn sind reines CSS (spiel.css) und hängen an den
   bestehenden Pop-ups (nestwerk.js). Alles Bewegte entfällt bei prefers-reduced-motion.
   Keine externen Quellen, keine Inline-Skripte (CSP); Bewegung per Web Animations API. */
(function () {
  "use strict";

  var SPEICHER_GUTHABEN = "nw-guthaben";
  var statusVorher = {};

  function reduziert() {
    return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  function frame(fn) {
    window.requestAnimationFrame(function () {
      window.requestAnimationFrame(fn);
    });
  }

  /* Fortschrittsbalken starten bei 0 und füllen sich weich; kurzes Glühen am Ende. */
  function fuellen(wurzel) {
    wurzel.querySelectorAll("progress.fortschritt:not([data-gefuellt])").forEach(function (balken) {
      balken.setAttribute("data-gefuellt", "");
      if (reduziert()) {
        return;
      }
      var ziel = balken.value;
      if (!ziel) {
        return;
      }
      balken.value = 0;
      frame(function () {
        balken.value = ziel;
        balken.setAttribute("data-fuellt", "");
        window.setTimeout(function () {
          balken.removeAttribute("data-fuellt");
        }, 1500);
      });
    });
  }

  function puls(el) {
    if (!el || reduziert()) {
      return;
    }
    el.classList.add("spiel-puls");
    el.removeAttribute("data-puls");
    void el.offsetWidth;
    el.setAttribute("data-puls", "");
  }

  function hochzaehlen(el, von, bis) {
    var start = null;
    function schritt(zeit) {
      if (!el.isConnected) {
        return;
      }
      if (start === null) {
        start = zeit;
      }
      var t = Math.min(1, (zeit - start) / 900);
      el.textContent = String(Math.round(von + (bis - von) * (1 - Math.pow(1 - t, 3))));
      if (t < 1) {
        window.requestAnimationFrame(schritt);
      } else {
        puls(el.closest(".punkte"));
      }
    }
    el.textContent = String(von);
    window.requestAnimationFrame(schritt);
  }

  /* Guthaben-Zähler: hat sich der Stand seit dem letzten Besuch erhöht, zählt er hoch. */
  function guthabenZaehler(wurzel) {
    var wert = wurzel.querySelector("[data-punkte-ziel] .punkte__wert");
    if (!wert || !/^\d+$/.test(wert.textContent.trim())) {
      return;
    }
    var jetzt = parseInt(wert.textContent, 10);
    var alt = null;
    try {
      var roh = window.sessionStorage.getItem(SPEICHER_GUTHABEN);
      alt = roh === null ? null : parseInt(roh, 10);
      window.sessionStorage.setItem(SPEICHER_GUTHABEN, String(jetzt));
    } catch (fehler) {
      return;
    }
    if (alt !== null && !isNaN(alt) && alt < jetzt && !reduziert()) {
      hochzaehlen(wert, alt, jetzt);
    }
  }

  /* Aufgabe geschafft: Haken und Leuchten an der Karte, Punkte fliegen in den Zähler (oder in die
     Kopfleiste, wenn auf dieser Seite keiner steht). */
  function statusMerken() {
    statusVorher = {};
    document.querySelectorAll(".aufgabe-karte[id]").forEach(function (karte) {
      statusVorher[karte.id] = karte.getAttribute("data-status");
    });
  }

  function fliegen(karte) {
    var quelle = karte.querySelector(".punkte");
    var wert = karte.querySelector(".punkte__wert");
    var ziel = document.querySelector("[data-punkte-ziel] .punkte__wert") ||
      document.querySelector(".kopf__zeile > .reihe") || document.querySelector(".kopf");
    if (!quelle || !wert || !ziel || reduziert() || !quelle.animate) {
      return;
    }
    var von = quelle.getBoundingClientRect();
    var nach = ziel.getBoundingClientRect();
    var chip = document.createElement("span");
    chip.className = "spiel-flug";
    chip.setAttribute("aria-hidden", "true");
    chip.textContent = "+" + wert.textContent.trim();
    document.body.appendChild(chip);
    var dx = nach.left + nach.width / 2 - von.left;
    var dy = nach.top + nach.height / 2 - von.top;
    var bahn = chip.animate([
      { transform: "translate(" + von.left + "px," + von.top + "px) scale(0.6)", opacity: 0 },
      { transform: "translate(" + von.left + "px," + (von.top - 24) + "px) scale(1.25)", opacity: 1, offset: 0.25 },
      { transform: "translate(" + (von.left + dx) + "px," + (von.top + dy) + "px) scale(0.7)", opacity: 0.9 }
    ], { duration: 1100, easing: "cubic-bezier(0.5, 0, 0.3, 1)" });
    bahn.onfinish = function () {
      chip.remove();
      puls(ziel.closest(".punkte") || ziel);
    };
  }

  function aufgabenPruefen(wurzel) {
    wurzel.querySelectorAll(".aufgabe-karte[id]").forEach(function (karte) {
      var neu = karte.getAttribute("data-status");
      var alt = statusVorher[karte.id];
      if (alt !== undefined && alt !== neu && (neu === "gemeldet" || neu === "bestaetigt")) {
        karte.setAttribute("data-fertig-anim", "");
        if (neu === "bestaetigt") {
          fliegen(karte);
        }
      }
    });
    statusMerken();
  }

  document.addEventListener("htmx:afterSettle", function () {
    fuellen(document);
    aufgabenPruefen(document);
  });

  document.addEventListener("DOMContentLoaded", function () {
    statusMerken();
    fuellen(document);
    guthabenZaehler(document);
  });
})();
