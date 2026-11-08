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

  /* Löschen (ⓧ): Popup statt Bestätigungsseite. Ohne JS bleibt der Link auf die Seite. */
  function dialog() { return document.getElementById("loeschen-dialog"); }

  document.addEventListener("click", function (e) {
    var oeffner = e.target.closest("[data-loeschen]");
    var zu = e.target.closest("[data-loeschen-zu]");
    var dlg = dialog();
    if (oeffner && dlg && typeof dlg.showModal === "function") {
      e.preventDefault();
      var form = dlg.querySelector("[data-loeschen-formular]");
      var serie = oeffner.hasAttribute("data-serie");
      form.setAttribute("action", oeffner.getAttribute("data-loeschen"));
      dlg.querySelector("[data-loeschen-name]").textContent = oeffner.getAttribute("data-titel") || "";
      dlg.querySelector("[data-loeschen-serie]").hidden = !serie;
      dlg.querySelectorAll("button[data-loeschen-serie]").forEach(function (b) { b.hidden = !serie; });
      dlg.querySelector("button[data-loeschen-einzeln]").hidden = serie;
      if (!dlg.open) { dlg.showModal(); }
      return;
    }
    if (zu && dlg) {
      dlg.close();
      return;
    }
    if (dlg && e.target === dlg) { dlg.close(); } // Hintergrund (::backdrop)
  });

  document.addEventListener("submit", function (e) {
    var form = e.target.closest ? e.target.closest("[data-loeschen-formular]") : null;
    if (!form || !window.htmx) { return; } // ohne htmx: normales Absenden (ganze Seite)
    e.preventDefault();
    var knopf = e.submitter;
    window.htmx.ajax("POST", form.getAttribute("action"), {
      target: "#wochenplan",
      swap: "outerHTML",
      values: {
        modus: knopf && knopf.value ? knopf.value : "tag",
        woche: form.querySelector("[name=woche]").value,
      },
    });
  });

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
