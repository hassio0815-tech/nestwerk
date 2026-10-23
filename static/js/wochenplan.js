/* Wochenplan (AP14): Ziehen mit SortableJS -> HTMX-POST. Ohne JS bleibt das Formular. */
(function () {
  "use strict";

  function ids(liste) {
    return Array.prototype.map
      .call(liste.querySelectorAll("[data-id]"), function (k) { return k.dataset.id; })
      .join(",");
  }

  function senden(ereignis) {
    var karte = ereignis.item;
    var ziel = ereignis.to;
    var url = karte.dataset.url;
    var plan = document.getElementById("wochenplan");
    var woche = plan.querySelector("[data-wochenplan-formular] [name=woche]").value;
    window.htmx.ajax("POST", url, {
      target: "#wochenplan",
      swap: "outerHTML",
      values: { datum: ziel.dataset.tag, reihenfolge: ids(ziel), woche: woche },
    });
  }

  function starten() {
    var plan = document.getElementById("wochenplan");
    if (!plan || !window.Sortable || !window.htmx) { return; }
    plan.querySelectorAll(".wochenplan__liste[data-tag]").forEach(function (liste) {
      window.Sortable.create(liste, {
        group: "wochenplan",
        animation: 150,
        draggable: "[data-beweglich]",
        filter: "input, button, label, a",
        preventOnFilter: false,
        delay: 150,
        delayOnTouchOnly: true,
        touchStartThreshold: 4,
        ghostClass: "wochenplan__karte--geist",
        onEnd: function (e) {
          if (e.from !== e.to || e.oldIndex !== e.newIndex) { senden(e); }
        },
      });
    });
  }

  /* Fehlerantworten (409/400) enthalten das neu gerenderte Brett samt Meldung:
     tauschen, damit die Karte zurückspringt. */
  document.addEventListener("htmx:beforeSwap", function (e) {
    var status = e.detail.xhr && e.detail.xhr.status;
    if ((status === 409 || status === 400) && e.detail.target && e.detail.target.id === "wochenplan") {
      e.detail.shouldSwap = true;
      e.detail.isError = false;
    }
  });
  document.addEventListener("htmx:afterSettle", starten);
  document.addEventListener("DOMContentLoaded", starten);
  window.addEventListener("load", starten);
})();
