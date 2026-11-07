/* Kalenderleiste der Anmeldeseite: Klick auf einen Tag öffnet sein Popup (ein <dialog> je Tag mit
   festen Aufgaben). Native <dialog>: Esc und Fokusführung kommen vom Browser, ein Klick auf den
   Hintergrund schließt zusätzlich. Ohne JavaScript bleibt die Leiste lesbar (ohne Popup). */
(function () {
  "use strict";

  var bereich = document.querySelector("[data-wochenvorschau]");
  if (!bereich || typeof HTMLDialogElement === "undefined") {
    return;
  }

  bereich.addEventListener("click", function (ereignis) {
    var knopf = ereignis.target.closest("[data-woche-tag]");
    if (knopf) {
      var dialog = document.getElementById(knopf.getAttribute("aria-controls") || "");
      if (dialog && !dialog.open) {
        dialog.showModal();
      }
      return;
    }
    // Hintergrund (::backdrop) meldet das <dialog> selbst als Ziel
    if (ereignis.target.matches("dialog.nw-woche__dialog")) {
      ereignis.target.close();
    }
  });
})();
