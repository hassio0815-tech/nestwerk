/* Leerlauf-Timer fürs Kiosk-Tablet (ARCHITECTURE 4.4). Kein Inline-Script, keine Abhängigkeiten.
   Touch/Klick/Taste setzt den Timer zurück und meldet sich (höchstens alle 30 s) per POST beim
   Server, damit dessen Leerlauf-Uhr mitläuft. Nach Ablauf: Abmelden-Formular absenden. */
(function () {
  "use strict";
  var wurzel = document.querySelector("[data-leerlauf]");
  if (!wurzel) return;

  var sekunden = parseInt(wurzel.getAttribute("data-sekunden"), 10);
  var warnung = parseInt(wurzel.getAttribute("data-warnung"), 10) || 0;
  var url = wurzel.getAttribute("data-aktiv-url");
  var formular = wurzel.querySelector("[data-leerlauf-form]");
  var hinweis = wurzel.querySelector("[data-leerlauf-warnung]");
  var token = formular.querySelector("input[name=csrfmiddlewaretoken]");
  var warnTimer = null;
  var endeTimer = null;
  var letzterPing = Date.now();

  function planen() {
    window.clearTimeout(warnTimer);
    window.clearTimeout(endeTimer);
    if (hinweis) hinweis.hidden = true;
    if (warnung > 0 && warnung < sekunden) {
      warnTimer = window.setTimeout(function () {
        if (hinweis) hinweis.hidden = false;
      }, (sekunden - warnung) * 1000);
    }
    endeTimer = window.setTimeout(function () {
      formular.submit();
    }, sekunden * 1000);
  }

  function ping() {
    if (!url || !token || Date.now() - letzterPing < 30000) return;
    letzterPing = Date.now();
    fetch(url, { method: "POST", headers: { "X-CSRFToken": token.value }, credentials: "same-origin" })
      .then(function (antwort) {
        if (antwort.status === 401 || antwort.redirected) formular.submit();
      })
      .catch(function () {});
  }

  function aktiv() {
    planen();
    ping();
  }

  ["pointerdown", "touchstart", "keydown", "click"].forEach(function (name) {
    document.addEventListener(name, aktiv, { passive: true });
  });
  planen();
})();
