/* FamKo Oberflaeche: Hell/Dunkel-Umschalter, PIN-Pad, Schliessen von Meldungen und Pop-ups.
   Keine externen Quellen, keine Inline-Skripte (CSP). */
(function () {
  "use strict";

  var COOKIE_MODUS = "famko_modus";
  var PIN_LAENGE = 4;

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
      var bereich = schliessen.closest("[data-schliessbar]");
      if (bereich) {
        bereich.remove();
      }
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
    var text = document.createElement("span");
    text.className = "toast__text";
    text.textContent = xhr.responseText || "Die Datei ist zu groß.";
    var knopf = document.createElement("button");
    knopf.type = "button";
    knopf.className = "knopf knopf--geist knopf--klein";
    knopf.setAttribute("data-schliessen", "");
    knopf.textContent = "Schließen";
    toast.appendChild(text);
    toast.appendChild(knopf);
    bereich.appendChild(toast);
  });

  document.querySelectorAll("[data-pin]").forEach(pinAktualisieren);
})();
