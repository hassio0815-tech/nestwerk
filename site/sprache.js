/* Sprachwahl der Landing Page: Englisch steht im HTML (auch ohne JavaScript), Deutsch kommt
   aus DE. Start: ?lang=, sonst gespeicherte Wahl, sonst Browser-Sprache, sonst Englisch.
   Deutsche Version zeigt die deutschen Screenshots (bilder/), englische bilder/en/. */
(function () {
  "use strict";

  var DE = {
    titel: "Nestwerk – das Familien-Dashboard für Aufgaben, Belohnungen und Lernen",
    sprung: "Zum Inhalt",
    nav: "Hauptnavigation",
    nav_funktionen: "Funktionen",
    nav_datenschutz: "Datenschutz",
    nav_technik: "Technik",
    h1: "Aufgaben, Belohnungen und Lernen für die ganze Familie",
    hero_text: "Nestwerk ist ein freies Familien-Dashboard, das ihr auf dem eigenen Server betreibt. Auf Deutsch und Englisch.",
    knopf_github: "Auf GitHub ansehen",
    knopf_installation: "Installation",
    link_installation: "https://github.com/hassio0815-tech/nestwerk/blob/main/docs/INSTALLATION.md",
    was_h: "Was ist Nestwerk?",
    was_1: "Nestwerk macht Haushalt und Mithelfen zum gemeinsamen Spiel. Kinder helfen freiwillig, sammeln dafür Punkte und tauschen sie gegen Belohnungen, die die Familie selbst festlegt.",
    was_2: "Jedes Kind baut sich einen eigenen Block-Avatar, steigt im Rang auf und sammelt Abzeichen. Als Familie arbeitet ihr gemeinsam auf ein Ziel hin.",
    was_3: "Eltern behalten mit einem ruhigen Dashboard die Übersicht und entscheiden, was zählt. Alles läuft lokal bei euch zu Hause, ohne Cloud und ohne Konto bei Dritten.",
    funktionen_h: "Funktionen",
    f1_h: "Aufgaben & Freigabe",
    f1_p: "Aufgaben anlegen, wiederholen und abhaken. Nachweise und Freigabe durch die Eltern halten es fair.",
    f2_h: "Punkte & Belohnungen",
    f2_p: "Freiwillige Hilfe zählt Punkte. Dafür gibt es Belohnungen aus einem Katalog, den ihr selbst festlegt.",
    f3_h: "Avatare & Mods",
    f3_p: "Jedes Kind baut seine Block-Figur aus Mods, die es sich im Mod-Shop erarbeitet.",
    f4_h: "Ränge, Serien & Abzeichen",
    f4_p: "Ränge von Common bis God Mode, Serien über Tage und Wochen und Abzeichen zum Sammeln.",
    f5_h: "Familienziel & Held der Woche",
    f5_p: "Alle zusammen auf ein Ziel hin, die Kinder stimmen ab. Der Held der Woche wird gefeiert.",
    f6_h: "Sondertag",
    f6_p: "Wer seine Mods komplett ausgebaut hat, verdient sich einen eigenen Sondertag.",
    f7_h: "Ruhmeshalle",
    f7_p: "Besondere Momente und Rekorde der Familie bleiben dauerhaft sichtbar.",
    f8_h: "Eltern-Dashboard",
    f8_p: "Offene Entscheidungen, Kinder, Sondertage und Einstellungen auf einen Blick.",
    f9_h: "Datenschutz & Selbst-gehostet",
    f9_p: "Läuft auf eurem eigenen Server. Keine Cloud, kein Tracking, keine Werbung.",
    f10_h: "Deutsch & Englisch",
    f10_p: "Jedes Familienmitglied wählt seine Sprache, auch Benachrichtigungen kommen in dieser Sprache.",
    f11_h: "Modular erweiterbar",
    f11_p: "Lernen und Forschen sind als nächste Module geplant. Neue Bausteine fügen sich in das gleiche System ein.",
    galerie_text: "Kinder-Ansichten sind dunkel und verspielt, die Eltern-Ansicht ist hell und ruhig. Ein Klick öffnet das Bild groß.",
    b1: "Kinder-Dashboard",
    b1_alt: "Das Dashboard eines Kindes mit Avatar, Punkten und offenen Aufgaben im dunklen Design.",
    b2: "Flur-Tablet",
    b2_alt: "Tablet-Startseite mit Familienziel und Ranking der Kinder.",
    b3: "Avatar-Galerie",
    b3_alt: "Galerie der Block-Avatare, aus denen jedes Kind sein Thema wählt.",
    b4: "Mod-Shop",
    b4_alt: "Der Mod-Shop mit Ausbaustufe, Schmiede und den Mods des Kindes.",
    b5: "Familienziel",
    b5_alt: "Gemeinsames Familienziel mit Fortschrittsbalken und Abstimmung für die nächste Woche.",
    b6: "Eltern-Dashboard",
    b6_alt: "Das helle Eltern-Dashboard mit offenen Entscheidungen, Kindern und Familienziel.",
    ds_h: "Datenschutz",
    ds_1: "Alle Daten bleiben auf eurem Server.",
    ds_2: "Keine Werbung, kein Tracking, keine externen Dienste, auch keine fremden Schriften oder CDNs.",
    ds_3: "Benachrichtigungen per eigenem Web-Push und eigenem Mailserver.",
    ds_4: "Kinder haben nur Benutzernamen und PIN, keine E-Mail-Adresse.",
    tech_h: "Technik",
    tech_p: "Nestwerk basiert auf Django und läuft in Docker. Als Progressive Web App lässt es sich auf dem Handy und dem Flur-Tablet wie eine App installieren. Die Oberfläche kommt ohne externe Ressourcen aus.",
    chip_self: "Selbst gehostet",
    lizenz_h: "Lizenz",
    lizenz_p: 'Nestwerk steht unter der <a href="https://www.gnu.org/licenses/agpl-3.0.html">GNU AGPL-3.0</a>. Der Quellcode ist offen.',
    fuss_lizenz: "Lizenz AGPL-3.0"
  };
  var SPEICHER = "nestwerk-sprache";
  var EN = {};

  function alle(attr, fn) {
    document.querySelectorAll("[" + attr + "]").forEach(function (el) {
      fn(el, el.getAttribute(attr));
    });
  }

  function englischMerken() {
    alle("data-i18n", function (el, k) { EN[k] = el.textContent; });
    alle("data-i18n-html", function (el, k) { EN[k] = el.innerHTML; });
    alle("data-i18n-alt", function (el, k) { EN[k] = el.getAttribute("alt"); });
    alle("data-i18n-aria", function (el, k) { EN[k] = el.getAttribute("aria-label"); });
    alle("data-i18n-href", function (el, k) { EN[k] = el.getAttribute("href"); });
  }

  function setzen(sprache) {
    var t = sprache === "de" ? DE : EN;
    var text = function (k) { return t[k] !== undefined ? t[k] : EN[k]; };
    document.documentElement.lang = sprache;
    alle("data-i18n", function (el, k) { el.textContent = text(k); });
    alle("data-i18n-html", function (el, k) { el.innerHTML = text(k); });
    alle("data-i18n-alt", function (el, k) { el.setAttribute("alt", text(k)); });
    alle("data-i18n-aria", function (el, k) { el.setAttribute("aria-label", text(k)); });
    alle("data-i18n-href", function (el, k) { el.setAttribute("href", text(k)); });
    alle("data-bild", function (el, datei) {
      var pfad = (sprache === "de" ? "bilder/" : "bilder/en/") + datei;
      el.setAttribute(el.tagName === "IMG" ? "src" : "href", pfad);
    });
    document.querySelectorAll("[data-sprache]").forEach(function (knopf) {
      knopf.setAttribute("aria-pressed", String(knopf.getAttribute("data-sprache") === sprache));
    });
    try { window.localStorage.setItem(SPEICHER, sprache); } catch (e) { /* privat */ }
  }

  function start() {
    var url = new URLSearchParams(window.location.search).get("lang");
    var gespeichert = null;
    try { gespeichert = window.localStorage.getItem(SPEICHER); } catch (e) { /* privat */ }
    var browser = (navigator.language || "en").slice(0, 2).toLowerCase();
    var wahl = [url, gespeichert, browser].filter(function (s) { return s === "de" || s === "en"; })[0] || "en";
    return wahl;
  }

  document.addEventListener("DOMContentLoaded", function () {
    englischMerken();
    var sprache = start();
    if (sprache !== "en") {
      setzen(sprache);
    }
    document.querySelectorAll("[data-sprache]").forEach(function (knopf) {
      knopf.addEventListener("click", function () { setzen(knopf.getAttribute("data-sprache")); });
    });
  });
})();
