/* Nestwerk Oberflaeche: Hell/Dunkel-Umschalter, PIN-Pad, Pop-up-Warteschlange (AP33), Schliessen.
   Keine externen Quellen, keine Inline-Skripte (CSP). */
(function () {
  "use strict";

  var COOKIE_MODUS = "nestwerk_modus";
  var PIN_LAENGE = 4;
  var MELDUNGEN_ID = "meldungen";
  var AKTIVES_POPUP = "#meldungen > [data-popup-aktiv]";
  var INTERAKTIV = "a, button, input, select, textarea, label, form, [data-festhalten]";

  function modusSetzen(modus) {
    document.body.setAttribute("data-modus", modus);
    document.cookie =
      COOKIE_MODUS + "=" + modus + "; path=/; max-age=31536000; SameSite=Lax";
  }

  function pinAktualisieren(pin) {
    var feld = pin.querySelector("[data-pin-feld]");
    var punkte = pin.querySelectorAll("[data-pin-punkt]");
    var ok = pin.querySelector("[data-pin-ok]");
    var wert = feld ? feld.value : "";

    punkte.forEach(function (punkt, index) {
      punkt.classList.toggle("pin__punkt--gefuellt", index < wert.length);
    });
    if (ok) {
      ok.disabled = wert.length !== PIN_LAENGE;
    }
  }

  function pinTaste(pin, ziffer) {
    var feld = pin.querySelector("[data-pin-feld]");
    if (feld && feld.value.length < PIN_LAENGE) {
      feld.value += ziffer;
      pinAktualisieren(pin);
    }
  }

  function pinLoeschen(pin) {
    var feld = pin.querySelector("[data-pin-feld]");
    if (feld) {
      feld.value = feld.value.slice(0, -1);
      pinAktualisieren(pin);
    }
  }

  /* Pop-ups (AP33): #meldungen zeigt nacheinander; jedes Pop-up blendet nach data-dauer (ms) aus,
     data-festhalten bleibt stehen. Ohne Bewegungserlaubnis nur Einblenden, Zahlen gleich fertig. */
  function bewegungReduziert() {
    return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  function schliessenMeldung(el) {
    if (!el || !el.isConnected) {
      return;
    }
    if (el.parentElement !== document.getElementById(MELDUNGEN_ID)) {
      el.remove();
      return;
    }
    if (el.hasAttribute("data-popup-weg")) {
      return;
    }
    el.setAttribute("data-popup-weg", "");
    window.setTimeout(function () {
      el.remove();
    }, bewegungReduziert() ? 0 : 200);
  }

  /* Serienbonus: die erste Zahl im Titel zaehlt von 0 hoch (reines Text-Update, kein Layout). */
  function zaehlen(el) {
    var ziel = el.querySelector("[data-zaehl]");
    var text = ziel ? ziel.textContent : "";
    var treffer = /\d+/.exec(text);
    if (!treffer || bewegungReduziert()) {
      return;
    }
    var bis = parseInt(treffer[0], 10);
    var start = null;
    function schritt(zeit) {
      if (!ziel.isConnected) {
        return;
      }
      if (start === null) {
        start = zeit;
      }
      var t = Math.min(1, (zeit - start) / 800);
      var wert = Math.round(bis * (1 - Math.pow(1 - t, 3)));
      ziel.textContent = text.replace(/\d+/, String(wert));
      if (t < 1) {
        window.requestAnimationFrame(schritt);
      }
    }
    ziel.textContent = text.replace(/\d+/, "0");
    window.requestAnimationFrame(schritt);
  }

  function startePopup(el) {
    var dauer = parseInt(el.getAttribute("data-dauer"), 10) || 6000;
    if (!el.hasAttribute("data-festhalten")) {
      window.setTimeout(function () {
        schliessenMeldung(el);
      }, dauer);
    }
    zaehlen(el);
  }

  /* Eine Warteschlange: genau ein Eintrag ist aktiv, alle anderen warten (display: none). */
  function warteschlange() {
    var bereich = document.getElementById(MELDUNGEN_ID);
    if (!bereich) {
      return;
    }
    var eintraege = Array.prototype.filter.call(bereich.children, function (el) {
      return el.hasAttribute("data-schliessbar");
    });
    var aktiv = eintraege.filter(function (el) {
      return el.hasAttribute("data-popup-aktiv");
    })[0];
    if (!aktiv && eintraege.length) {
      aktiv = eintraege[0];
      aktiv.removeAttribute("data-popup-wartet");
      aktiv.setAttribute("data-popup-aktiv", "");
      startePopup(aktiv);
    }
    eintraege.forEach(function (el) {
      if (el !== aktiv) {
        el.setAttribute("data-popup-wartet", "");
      }
    });
  }

  var meldungen = document.getElementById(MELDUNGEN_ID);
  if (meldungen) {
    var beobachter = new MutationObserver(warteschlange);
    beobachter.observe(meldungen, { childList: true });
    warteschlange();
  }

  document.addEventListener("keydown", function (ereignis) {
    if (ereignis.key === "Escape") {
      schliessenMeldung(document.querySelector(AKTIVES_POPUP));
    }
  });

  /* Abzeichen-Grafik fehlt: Platzhalter-Icon zeigen (Ereignis ohne Inline-Handler, CSP-konform). */
  document.addEventListener("error", function (ereignis) {
    var bild = ereignis.target;
    if (bild instanceof HTMLImageElement && bild.hasAttribute("data-bild-ersatz")) {
      bild.hidden = true;
      if (bild.nextElementSibling) {
        bild.nextElementSibling.hidden = false;
      }
    }
  }, true);

  document.addEventListener("click", function (ereignis) {
    var ziel = ereignis.target;
    if (!(ziel instanceof Element)) {
      return;
    }

    var umschalter = ziel.closest("[data-modus-umschalter]");
    if (umschalter) {
      var neu = document.body.getAttribute("data-modus") === "hell" ? "dunkel" : "hell";
      modusSetzen(neu);
      return;
    }

    var pin = ziel.closest("[data-pin]");
    if (pin) {
      var taste = ziel.closest("[data-pin-taste]");
      if (taste) {
        pinTaste(pin, taste.getAttribute("data-pin-taste"));
        return;
      }
      if (ziel.closest("[data-pin-loeschen]")) {
        pinLoeschen(pin);
        return;
      }
    }

    var schliessen = ziel.closest("[data-schliessen]");
    if (schliessen) {
      schliessenMeldung(schliessen.closest("[data-schliessbar]"));
      return;
    }

    /* Tippen auf ein aktives Pop-up schliesst es; Eingabefelder und Festhalten-Dialoge nicht. */
    var aktiv = ziel.closest(AKTIVES_POPUP);
    if (aktiv && !ziel.closest(INTERAKTIV)) {
      schliessenMeldung(aktiv);
    }
  });

  /* Polling pausiert bei verstecktem Tab (Elemente mit data-nur-sichtbar). Ersetzt Trigger-Filter
     wie "every 10s [document.visibilityState === 'visible']": die braeuchten eval und damit
     'unsafe-eval' in der CSP (htmx.config.allowEval ist aus). */
  document.addEventListener("htmx:beforeRequest", function (e) {
    var el = e.detail && e.detail.elt;
    if (document.hidden && el instanceof Element && el.hasAttribute("data-nur-sichtbar")) {
      e.preventDefault();
    }
  });

  /* HTMX tauscht Fehlerantworten nicht: zu große Uploads (413, Text vom Server) als Toast zeigen. */
  document.addEventListener("htmx:responseError", function (e) {
    var xhr = e.detail && e.detail.xhr;
    var bereich = document.getElementById("meldungen");
    if (!xhr || xhr.status !== 413 || !bereich) {
      return;
    }
    var toast = document.createElement("div");
    toast.className = "toast toast--fehler";
    toast.setAttribute("role", "status");
    toast.setAttribute("data-schliessbar", "");
    toast.setAttribute("data-dauer", "9000");
    var text = document.createElement("span");
    text.className = "toast__text";
    text.textContent = xhr.responseText || document.body.getAttribute("data-text-zu-gross") || "Die Datei ist zu groß.";
    var knopf = document.createElement("button");
    knopf.type = "button";
    knopf.className = "knopf knopf--geist knopf--klein";
    knopf.setAttribute("data-schliessen", "");
    knopf.textContent = document.body.getAttribute("data-text-schliessen") || "Schließen";
    toast.appendChild(text);
    toast.appendChild(knopf);
    bereich.appendChild(toast);
  });

  document.querySelectorAll("[data-pin]").forEach(pinAktualisieren);
})();
