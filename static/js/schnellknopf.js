/* Schnell-Knöpfe (Eltern): "Drücken" öffnet das Auswahlfenster (<dialog>) des Knopfs. Die Ereignisse
   hängen am Dokument, damit sie auch nach einem HTMX-Austausch der Kachel funktionieren. Esc und
   Fokusführung kommen vom Browser, ein Klick auf den Hintergrund schließt zusätzlich. */
(function () {
  "use strict";

  if (window.nwSchnellknopfGeladen || typeof HTMLDialogElement === "undefined") {
    return;
  }
  window.nwSchnellknopfGeladen = true;

  document.addEventListener("click", function (ereignis) {
    var ziel = ereignis.target;
    var oeffner = ziel.closest("[data-knopf-dialog]");
    if (oeffner) {
      var dialog = document.getElementById(oeffner.getAttribute("data-knopf-dialog") || "");
      if (dialog) {
        ereignis.preventDefault(); // Link ohne JavaScript = Bestätigungsseite
        if (!dialog.open) {
          dialog.showModal();
        }
      }
      return;
    }
    var zu = ziel.closest("[data-knopf-schliessen]");
    if (zu) {
      var offen = zu.closest("dialog");
      if (offen) {
        offen.close();
      }
      return;
    }
    // Hintergrund (::backdrop) meldet das <dialog> selbst als Ziel
    if (ziel.matches("dialog.knopf-dialog")) {
      ziel.close();
    }
  });

  // Ein Kind gewählt -> "Bestimmtes Kind" ist gemeint
  document.addEventListener("change", function (ereignis) {
    var wahl = ereignis.target.closest("[data-knopf-kind]");
    if (wahl && wahl.value) {
      var radio = wahl.closest("form").querySelector('input[name="modus"][value="ich_machs"]');
      if (radio) {
        radio.checked = true;
      }
    }
  });
})();
