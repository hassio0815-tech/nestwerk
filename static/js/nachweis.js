/* Nachweis-Foto (AP13): Vorschau und Verkleinerung vor dem Upload. Keine externen Quellen,
   keine Inline-Skripte (CSP). Der Server prüft und kodiert trotzdem neu (EXIF wird dort entfernt). */
(function () {
  "use strict";

  var MAX_KANTE = 1600;
  var QUALITAET = 0.8;

  function vorschauSetzen(feld, url) {
    var kasten = feld.closest("[data-nachweis]");
    var bild = kasten && kasten.querySelector("[data-nachweis-vorschau]");
    if (!bild) return;
    if (url) {
      bild.src = url;
      bild.hidden = false;
    } else {
      bild.removeAttribute("src");
      bild.hidden = true;
    }
  }

  function alsDatenUrl(datei, fertig) {
    var leser = new FileReader();
    leser.onload = function () { fertig(leser.result); };
    leser.onerror = function () { fertig(null); };
    leser.readAsDataURL(datei);
  }

  function verkleinern(datei, fertig) {
    var url = URL.createObjectURL(datei);
    var bild = new Image();
    bild.onload = function () {
      URL.revokeObjectURL(url);
      var faktor = Math.min(1, MAX_KANTE / Math.max(bild.naturalWidth, bild.naturalHeight));
      if (faktor >= 1 && datei.size < 1.5 * 1024 * 1024) { fertig(datei); return; }
      var leinwand = document.createElement("canvas");
      leinwand.width = Math.max(1, Math.round(bild.naturalWidth * faktor));
      leinwand.height = Math.max(1, Math.round(bild.naturalHeight * faktor));
      leinwand.getContext("2d").drawImage(bild, 0, 0, leinwand.width, leinwand.height);
      leinwand.toBlob(function (blob) {
        if (!blob || blob.size >= datei.size) { fertig(datei); return; }
        fertig(new File([blob], "nachweis.jpg", { type: "image/jpeg" }));
      }, "image/jpeg", QUALITAET);
    };
    // Nicht dekodierbar (z. B. HEIC im Desktop-Browser): Original senden, der Server übernimmt.
    bild.onerror = function () { URL.revokeObjectURL(url); fertig(datei); };
    bild.src = url;
  }

  document.addEventListener("change", function (e) {
    var feld = e.target;
    if (!feld.matches || !feld.matches("input[type=file][data-nachweis-feld]")) return;
    var datei = feld.files && feld.files[0];
    if (!datei) { vorschauSetzen(feld, null); return; }
    verkleinern(datei, function (ergebnis) {
      if (ergebnis !== datei && window.DataTransfer) {
        try {
          var behaelter = new DataTransfer();
          behaelter.items.add(ergebnis);
          feld.files = behaelter.files;
        } catch (fehler) { /* Original bleibt, der Server verkleinert */ }
      }
      alsDatenUrl(ergebnis, function (url) { vorschauSetzen(feld, url); });
    });
  });
})();
