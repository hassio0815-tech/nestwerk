# Nestwerk: Produktspezifikation

- **Stand:** 23.10.2026
- **Quellen:** Konzept "Familien-App: Konzept und Entscheidungsstand" (23.10.2026) und die bestätigten Interview-Entscheidungen 1–27. Die Entscheidungen haben Vorrang vor dem Konzept.
- **Zweck:** Verbindliche Grundlage für die Umsetzung.

## Kennzeichnung

- **[E]** Verbindlich. Konzept-[E] und/oder Entscheidung.
- **[V]** Vorschlag. Weder bestätigt noch ersetzt. Vor Umsetzung prüfen, Änderungen begründen.
- **[O]** Offen. Siehe Abschnitt 19.
- **(E1)** = Entscheidung 1. **(Konzept 4.2)** = Konzept-Abschnitt.

---

## 0. Grundregeln

- **[E] Alle Regeln und Werte sind änderbar.** Sie liegen in der Datenbank und werden im Eltern-Dashboard gepflegt. Nichts ist hart im Code. (E22)
- **[E] Modulare Architektur.** Jede Funktion ist ein eigenes Django-App-Modul: `aufgaben`, `belohnung`, `avatar`. Später: `lernen`, `forschen`. (E6)
- **[E] Gemeinsame Basis für alle Module:** Benutzer, Punkte (Ledger), Benachrichtigungen, Ereignisse, Einstellungen. (E6)
- **[E] Spätere Module (Lernsystem, Forschungssystem)** ergänzen Regeln, Meilensteine, Abzeichen und Benachrichtigungskanäle über die Datenbank. (E1, E12, E24)
- **[E] Pädagogischer Grundsatz:** Alle Aufgaben sind freiwillig. Keine Pflichtaufgaben, keine Strafen, keine Punktabzüge. (Konzept 1)

---

## 1. Ziel und Rahmen

- **[E]** Familien-App, nutzbar im Webbrowser und auf dem iPhone über Safari. Gut lesbar und mobil bedienbar.
- **[E]** Startpunkt: Belohnungssystem für freiwillige Hilfe im Haushalt. Beispiele: Putzen, Müll rausbringen, Leergut wegbringen, Rasen mähen, Einkaufsliste, Wäsche und weitere.
- **[E]** Die App wird später schrittweise erweitert. Geplant sind Lernsystem, Anbindung an Home Assistant und weitere Familienfunktionen.
- **[E]** Nutzer (Referenzfamilie): zwei Elternteile und drei Kinder.
- **[E]** Pädagogisches Ziel: Die Kinder unterstützen aus eigenem Antrieb den Familienalltag. Die Eltern haben nach der Arbeit mehr Zeit für die Familie.
- **[E]** Die Kinder lernen, selbst abzuwägen, wofür sie ihre Punkte einsetzen. Beispiel: Süßes und Gaming jetzt, oder Avatar und Sondertag langfristig.
- **[E]** Betrieb: Debian-VM auf einem Proxmox-Server zu Hause, 24/7 (siehe 16). Die Kinder nutzen die App nur im Heimnetz. Die Eltern erreichen sie unterwegs über das bestehende VPN (siehe 14).
- **[V]** Oberflächensprache Deutsch.
- **[O]** Zeitzone: Standard Europe/Berlin, noch nicht bestätigt (siehe 19).
- **[E]** Name: **Nestwerk** (exakte Schreibweise, großes K). Der Anzeigename ist in den Einstellungen änderbar. (E8)

---

## 2. Rollen und Zugang

- **[E]** Zwei Ebenen: getrennte Eltern-Ebene mit eigenem Dashboard und Kinder-Ebene.
- **[E] Eltern-Zugang:** ein gemeinsames Passwort. Bei der Anmeldung geben die Eltern ihren Namen an.
- **[E]** Die App protokolliert damit, welcher Elternteil welche Aktion ausgeführt hat (Genehmigung, Bonus, Nachricht, Änderung).
- **[E]** Die Zuordnung beruht auf der Namensangabe und ist nicht fälschungssicher. Das ist akzeptiert.
- **[E] Kinder-Zugang:** Tippen auf das eigene Avatar-Bild, dann persönliche vierstellige PIN.
- **[V]** Passwort und PINs werden gehasht gespeichert.
- **[V]** Falsche PIN-Eingaben werden begrenzt (Rate-Limit mit kurzer Sperre).
- **[V]** Eltern bleiben auf einem vertrauten Gerät angemeldet (langlebige Sitzung).
- **[E] Kinder-Sitzungen:** Auf dem Kinder-Tablet läuft die Sitzung nach ca. 5 Minuten Inaktivität ab. Auf den eigenen iPhones bleiben Kinder angemeldet. (E17)
- **[E]** Beide Elternteile haben dieselben Rechte (Aufgaben, Punkte, Katalog, Freigaben).
- **[E]** Namen von Eltern und Kindern werden im Einrichtungs-Assistenten erfasst (siehe 4).
- **[E]** Eltern haben einen Avatar: einfache Blockfigur, ohne Mods, Punkte und Rang (siehe 11). Eltern sind nicht im Ranking. (E10)

---

## 3. Geräte und Kiosk-Tablet (neu)

- **[E] Hauptgerät der Kinder: gemeinsames Android-Tablet im Flur.** (E17)
  - Anmeldung: Avatar antippen, PIN eingeben.
  - Auto-Logout nach ca. 5 Minuten Inaktivität.
  - Familien-Ranking sichtbar.
  - Betrieb im Kiosk-Browser (z. B. Fully Kiosk).
  - Familienziel-Leiste mit Beiträgen der Kinder (siehe 8).
  - Kann später zum zentralen Familien-Display werden (Kalender, Home Assistant, Lernen).
- **[E] Zweitgerät: eigene iPhones der Kinder als PWA** auf dem Home-Bildschirm. (E17)
  - Bleiben angemeldet.
  - Eigene Push-Nachrichten, z. B. "Aufgabe bestätigt", "Mod fertig".

---

## 4. Einrichtungs-Assistent (neu)

- **[E]** Alle Ersteinrichtungsdaten erfasst ein Assistent in der App, nicht im Code. (E7)
- **[E]** Der Assistent erfasst:
  - Namen der Eltern und Kinder
  - vierstellige PINs der Kinder
  - Eltern-Passwort
  - E-Mail-Adressen der Eltern (Empfänger)
  - SMTP-Zugang (eigenes Postfach auf eigener Domain, siehe 13)
  - Go-live-Datum (Startpunkt des App-Jahres, siehe 10)
  - Zeitzone [O]
  - Startwerte: Ränge, Katalog, Taschengeld-Limit, Aufgabenbibliothek, Familienziel (siehe 18)
- **[E]** Alle Startwerte sind vorausgefüllt und danach änderbar. (E13, E14, E15)

---

## 5. Aufgaben

### 5.1 Anlegen und Felder

- **[E]** Beide Eltern legen Aufgaben im Eltern-Dashboard über Formularfelder an.
- **[E]** Jede Aufgabe wird einzeln bewertet. Es gibt keine fest vorgegebenen Maßnahmen und keine Pflichtfelder für Zeitpunkte. Alles bleibt so offen wie möglich, weil sich Aufgaben mit dem Alter der Kinder und mit dem Haushalt ändern.
- **[V]** Pflicht sind nur Titel und Punktwert. Alle anderen Felder sind optional:
  - Beschreibung
  - Punktwert (gilt für alle Kinder)
  - Freigabeart: Vertrauen, Eltern bestätigen, Foto-/Text-Nachweis
  - Zeitpunkt oder Zeitfenster
  - Wiederholung: einmalig, wiederkehrend (z. B. wöchentlich an bestimmten Wochentagen) oder in einem Intervall
  - Zuweisung an ein bestimmtes Kind
  - Limit pro Zeitraum (z. B. höchstens einmal pro Woche, damit Punkte nicht durch Wiederholen entstehen)
  - Kategorie (siehe 5.2) [E]
  - Status: aktiv, pausiert, beendet
- **[E]** Beispiel: Mülltonnen rausstellen jeden Mittwochabend, weil dienstags die Müllabfuhr kommt. Dasselbe Formular deckt Aufgaben ohne Termin und einmalige Aufgaben ab.
- **[E]** Planung wiederkehrender und terminierter Aufgaben mit Formularfeldern und Drag-and-Drop (z. B. Wochenansicht). Jede Aufgabe lässt sich auch ohne Ziehen über die Formularfelder setzen.
- **[E]** Aufgaben lassen sich jederzeit ändern, pausieren oder beenden. Bereits vergebene Punkte bleiben unverändert.

### 5.2 Aufgabenbibliothek und Kategorien

- **[V]** Aufgabenbibliothek mit Vorlagen (Titel, Punktwert, Freigabeart). Per Klick als Aufgabe aktivierbar und dabei anpassbar.
- **[V]** Aufgaben mit Wiederholung legt die Bibliothek ebenfalls als Vorlage ab.
- **[E]** Startvorlagen (siehe 18). Eltern können Vorlagen jederzeit anlegen, ändern und löschen. (E15)
- **[E]** Kategorien, bearbeitbar und mit Symbol: Haushalt, Küche, Wäsche, Garten, Schule, Sonstiges. Die Kategorie "Schule" ist die Brücke zum späteren Lernmodul. (E16)

### 5.3 Punktbewertung

- **[E]** Ein Punkt entspricht ungefähr einer Minute Aufwand. Das ist ein Richtwert für die Eltern, keine feste Regel.
- **[E]** Die Eltern bewerten jede Aufgabe selbst. Beispiele: Rasen mähen 45 Punkte, Bad putzen mehr als Flur saugen.
- **[E]** Keine Unterscheidung nach Alter. Alle Kinder erhalten für dieselbe Aufgabe denselben Punktwert.
- **[E] Sonderpunkte:** Nach der Bestätigung können die Eltern Bonuspunkte mit kurzer Begründung vergeben (z. B. "sehr gründlich"). So lassen sich Alter, Kenntnisstand und besondere Mühe ausgleichen.
- **[V]** Das Kind sieht Bonus und Begründung.
- **[V]** Optionale Obergrenze pro Aufgabe für Sonderpunkte: Standard 50 % des Aufgabenwerts, abschaltbar (siehe 18).

### 5.4 Ablauf

- **[E]** Wiederkehrende Aufgaben werden automatisch erzeugt und erscheinen im Kinder-Dashboard unter "Offene Aufgaben".
- **[E]** Die Kinder wählen selbst, welche sie übernehmen, um Punkte zu sammeln.
- **[E] Mehrere Interessenten:** Wählen mehrere Kinder dieselbe Aufgabe, bleibt sie für alle reserviert. Die Eltern entscheiden und weisen sie einem Kind zu. Die anderen sehen sie als vergeben.
- **[V] Ein Interessent:** Wählt nur ein Kind die Aufgabe, ist sie für dieses Kind reserviert. Die Eltern können die Reservierung lösen.
- **[E]** Das Kind meldet die Aufgabe als erledigt, bei Bedarf mit Foto oder Textnachricht. Die Eltern bestätigen.
- **[E]** Die Freigabeart ist pro Aufgabe gemischt: Vertrauen, Eltern bestätigen, Foto.
- **[V] Vertrauen:** Punkte werden sofort gutgeschrieben. Die Eltern können nachträglich korrigieren.
- **[E] Nachweise:** Fotos und Textnachrichten werden sofort gelöscht, sobald die Eltern die Aufgabe bestätigen. Im Protokoll bleibt nur der Vermerk, wer wann was bestätigt hat, ohne Foto und Text.
- **[V]** Bei Ablehnung oder Rückfrage bleibt der Nachweis bis zur Klärung bestehen und wird danach gelöscht.

### 5.5 Reservierung und Ablauf (neu)

- **[E]** Eine Reservierung läuft ab:
  - zeitgebundene Aufgabe: mit ihrer Frist
  - ungebundene Aufgabe: nach 48 Stunden
- **[E]** Das Kind erhält 6 Stunden vor Ablauf eine Push-Erinnerung.
- **[E]** Nach Ablauf ist die Aufgabe wieder frei. Die Eltern werden informiert. Keine Strafe.
- **[E]** Alle Werte sind einstellbar (siehe 18). (E22)

### 5.6 Verfall nicht übernommener Aufgaben (neu)

- **[E] Wiederkehrend mit Zeitfenster:** Die Aufgabe ist sichtbar, bis das Fenster endet. Dann läuft sie still ab, ohne Meldung an die Kinder. Die Eltern sehen sie als "nicht übernommen". Die Eltern erhalten 3 Stunden vor Ablauf eine Push-Nachricht.
- **[E] Wiederkehrend ohne Zeitfenster:** Es entsteht kein Stapel. Eine neue Instanz wird erst erzeugt, wenn die vorherige erledigt oder abgelaufen ist.
- **[E]** Kein Punkteabzug, keine Strafe.
- **[E]** Alle Werte sind einstellbar (siehe 18). (E23)

---

## 6. Punkte, Ränge und Kontinuität

### 6.1 Zwei Zähler pro Kind

- **[E]** Der Punktwert einer Aufgabe ist zugleich Einlösepunkt und Erfahrungspunkt (XP). Es gibt keinen getrennten XP-Wert.
- **[E] Guthaben:** steigt mit jeder Aufgabe. Sinkt beim Einlösen und beim Kauf von Mods.
- **[E] Gesamtpunkte (XP):** steigen mit jeder Aufgabe und sinken nie. Der Rang richtet sich nach diesem Wert.
- **[V]** Jede Punktbewegung ist ein unveränderlicher Ledger-Eintrag. Salden werden daraus berechnet.
- **[V]** Zusätzlich ein Audit-Log mit Elternteil, Aktion und Zeitpunkt.
- **[E]** Die Kinder entscheiden selbst, wofür sie Guthaben einsetzen: Süßes, Fernsehzeit, Gaming- oder Computerzeit, Taschengeld, Sonstiges oder Avatar-Mods. Eine Aufgabe legt keine Verwendung fest.
- **[E]** Die Kinder sollen motiviert sein, auch höher bewertete Aufgaben zu übernehmen, um schneller aufzusteigen.
- **[E]** Es gibt keine feste Wochenvorgabe an Punkten pro Kind. Wer mehr will, macht mehr. (Das Familienziel ist ein Gemeinschaftsziel, siehe 8.)

### 6.2 Ränge

- **[E]** Einheitliche Rangstufen für alle Kinder, in Art von Spiel-Seltenheiten: Common, Uncommon, Rare, Epic, Legendary, God Mode.
- **[V]** Rangnamen in der Elternansicht umbenennbar.
- **[E] Aufstieg:** Punkteschwelle (Gesamtpunkte) plus Mindestzahl aktiver Wochen.
- **[E] Aktive Woche:** Woche mit mindestens einer bestätigten Aufgabe.
- **[E]** Aktive Wochen werden insgesamt gezählt und nie zurückgesetzt. Wochen ohne Aufgabe kosten nichts, zählen aber nicht.
- **[E]** Lebensalter ist kein Kriterium. Die Zeitregeln gelten für alle gleich.
- **[E] Startwerte:** Schwellen, Mindestwochen und Mod-Preise je Rang siehe 18. Sie sind Startwerte und werden anhand der echten Wochenleistung kalibriert. (E14)
- **[E]** Planungsziel: Der Rang- und Mod-Aufbau reicht für ein Probejahr und bis etwa 1,5 Jahre, ohne dass ein fleißiges Kind vorher am Ende ist.
- **[E] God Mode:** Das Konzept sah God Mode als reinen Prestige-Rang vor. Entscheidung 1 ergänzt: Danach alle 26 aktiven Wochen ein Sondertag und ein neues Mod-Set, endlos (siehe 10 und 11). Titel, Aura, Pop-up und Abzeichen bleiben.
- **[V] Prognose:** Die App berechnet pro Kind aus dem Durchschnitt der letzten Wochen, wann der nächste Rang und der nächste Sondertag erreicht werden. Die Eltern sehen die Abweichung vom Ziel von zwei Sondertagen pro Jahr. Seite „Prognose & Kalibrierung“ mit Ampel, Empfehlung per Simulation und Übernahme per Klick; das Kind sieht nur „Nächster Rang voraussichtlich in ca. X Wochen“ (abschaltbar). Wirken die XP-Schwellen nie, lässt sich das Tempo über einen Faktor auf die Mindest-Aktivwochen pro Kind einstellen.
- **[E] Kalibrierung:** Nach 4–6 Wochen Prognose prüfen. Schwellen, Mod-Preise und Bauzeiten pro Kind mit einem Faktor nachstellen. Annahme für die Startwerte: 150–200 Punkte pro Woche. (E14)

### 6.3 Serie, Serienbonus und Meilensteine

- **[E]** Kontinuität wird honoriert. Wer regelmäßig hilft, steigt schneller auf als jemand, der in einer Woche viel sammelt und dann pausiert.
- **[E] Wochenserie:** Jede aktive Woche in Folge erhöht die Serie um 1.
- **[E] Serienbonus:** Ab Serie 2 gibt es einen Bonus auf die Aufgabenpunkte, +5 % pro Serienwoche, höchstens +25 %. Werte siehe 18. (E4)
- **[E]** Der Bonus wird sofort pro Aufgabe als eigener Ledger-Eintrag "Serienbonus" gebucht. Er wird auf ganze Punkte aufgerundet. Er erhöht Guthaben und Gesamtpunkte gleichermaßen.
- **[O]** Bezugswoche: Gilt für den Bonus die laufende Serie oder die vorherige, abgeschlossene Woche? (siehe 19)
- **[E]** Fällt eine Woche aus, beginnt die Serie bei 0. Punkte, Rang und aktive Wochen bleiben erhalten.
- **[E]** Pausierte Wochen und Tage sind neutral. Die Serie bricht nicht (siehe 7).
- **[E] Tagesserie:** Tage in Folge mit mindestens einer bestätigten Aufgabe. Bringt Abzeichen, keine Zusatzpunkte.
- **[E] Abzeichen (Meilensteine):** Tagesserie 7, 14, 30 Tage. Wochenserie 1, 2, 4, 8, 12, 24, 48 Wochen. Quartal mit durchgehend aktiven Wochen. Ein Abzeichen je Rangaufstieg. (E12)
- **[E]** Abzeichen geben nie Punkte. Sie werden im Profil gezeigt und als Pop-up angekündigt.
- **[E]** Serie, Abzeichen und Meilensteine sind im Dashboard sichtbar.
- **[E]** Abzeichen-Regeln liegen in der Datenbank. Module können eigene Abzeichen ergänzen. (E12)
- **[O]** Gestaltung der Abzeichen (siehe 19).

---

## 7. Pause-Schalter (neu)

- **[E]** Der Pause-Schalter ersetzt den Joker pro Quartal. Der Joker entfällt. (E3)
- **[E]** Die Eltern setzen die Pause im Eltern-Dashboard, für ein Kind oder die ganze Familie.
- **[E]** Pausierte Wochen und Tage sind neutral: Die Serie bricht nicht.
- **[E]** Aufgaben während der Pause zählen normal: Punkte, aktive Woche, Serie +1.
- **[E]** Pausen werden als Zeiträume (von–bis) gespeichert. Der Elternteil wird im Audit-Log vermerkt.
- **[E]** Das Kind sieht "Pause – deine Serie ist sicher".
- **[E]** Pausierte Kinder müssen beim Familienziel keine Aufgabe erledigen (siehe 8).
- **[E]** Später kann Home Assistant die Pause automatisch setzen.

---

## 8. Familienziel und Familien-Ranking (neu)

### 8.1 Familienziel

- **[E]** Gemeinschaftsziel: Die Summe der verdienten XP aller Kinder in einer Woche (Montag bis Sonntag) zählt. Nichts wird vom Guthaben abgezogen. (E26)
- **[E] Startziel:** 450 Punkte pro Woche.
- **[E] Bedingung:** Jedes nicht pausierte Kind hat mindestens eine bestätigte Aufgabe.
- **[E] Erfolg:** Konfetti-Pop-up beim Kind und Push an die Eltern.
- **[E]** Der Fortschritt steht als große Leiste auf dem Flur-Tablet, mit den Beiträgen der Kinder.
- **[E] Familienbelohnungen:** Die Eltern pflegen eine Liste (Startliste: Pizza, Spieleabend, Kino, Eis, Grillen).
- **[E] Zielwahl:** Die Kinder stimmen sonntags für das Ziel der Folgewoche ab. Bei Gleichstand entscheiden die Eltern.
- **[E] Großziel:** Nach 4 Wochenzielen in Folge wird ein großes Ziel freigeschaltet (Beispiel: Ausflug).
- **[E]** Alle Werte sind einstellbar (siehe 18).
- **[E]** Es gibt keine individuelle Wochenvorgabe pro Kind und keine Strafe bei Verfehlen.

### 8.2 Familien-Ranking

- **[E]** Die Kinder sehen die Familie als Fortschrittsschaufenster: Avatare, Rang, Mods, Abzeichen und Serie nebeneinander. (E25)
- **[E] "Held der Woche":** Das Kind mit dem größten Zuwachs gegenüber seinem eigenen Durchschnitt.
- **[E]** Rohpunkte sind sichtbar, aber nachrangig.
- **[E]** Die Ansicht ist im Eltern-Dashboard umschaltbar. Welche Modi genau, siehe 19.
- **[E]** Das Ranking ist auf dem Flur-Tablet sichtbar.
- **[E]** Eltern sind nicht im Ranking. (E10)

---

## 9. Einlösen und Belohnungskatalog

- **[E]** Die Eltern pflegen einen Belohnungskatalog mit festen Einträgen und Preisen in Punkten.
- **[E] Kategorien:** Süßes, Fernsehzeit, Gaming- und Computerzeit, Taschengeld, Sonstiges.
- **[E] Taschengeld:** feste Katalogeinträge (ein Betrag gegen eine Punktzahl) mit einem monatlichen Limit pro Kind. Die Eltern stellen das Limit ein.
- **[E] Einlöseantrag:** Das Kind stellt einen Antrag. Er erscheint im Eltern-Dashboard. Beide Eltern werden sofort benachrichtigt. Ein Elternteil bestätigt oder lehnt ab.
- **[E] Abbuchung erst bei Bestätigung:** Das Guthaben wird erst bei Bestätigung um den Preis gekürzt.
- **[V] Offene Anträge zählen gegen das Guthaben:** Ein Kind kann nicht mehr beantragen, als es abzüglich offener Anträge besitzt. Bei Ablehnung fällt der Antrag weg, es erfolgt keine Abbuchung.
- **[E]** Die technische Freischaltung (Geräte, Gaming-, TV- oder Internetzeit) erfolgt außerhalb der App durch die Eltern. Die App steuert nichts und braucht keine Anbindung an Router oder iOS-Bildschirmzeit.
- **[E]** Startwerte siehe 18.

---

## 10. Sondertag

- **[E]** Der Sondertag ist ein individueller Tag eines Kindes mit einem Elternteil (z. B. Sportveranstaltung, Ausflug, Kino, Essen gehen). Es gibt keinen festen Katalog: Das Kind wünscht sich frei.
- **[E] Freischaltung:** Das Kind erreicht einen Rang und in diesem Rang die Ausbaustufe 6 (alle sechs Slots gebaut). (E1)
- **[E] Meilensteine:** Rang 2, 3, 4 und 5 je einmal.
- **[E] God Mode:** Danach alle 26 aktiven Wochen ein Sondertag plus neues Mod-Set, endlos. Ob der Meilenstein in God Mode zusätzlich gilt, siehe 19. (E1)
- **[E]** Kein Punktepreis. Die Investition in Mods ist der Nachweis. Das Kind soll abwägen, ob es Punkte für Gaming und Süßes ausgibt oder in Mods investiert.
- **[E] Frühe Freischaltung** geht nicht verloren. Sie steht als "verdient, einlösbar ab Datum X" bereit. (E1)
- **[E] Obergrenzen:**
  - Ziel ist etwa zwei Sondertage pro Kind und Jahr. Das ist die organisatorische Obergrenze.
  - Höchstens 2 Sondertage pro Kind und App-Jahr. Das App-Jahr beginnt am Go-live-Datum (in den Einstellungen gespeichert). (E1)
  - Mindestabstand 150 Tage zwischen zwei Sondertagen desselben Kindes. (E1)
  - Die Grenzen werden im System erzwungen.
- **[V] Bezugsdatum** für den Mindestabstand ist das Datum der Annahme. Die Eltern können es korrigieren.
- **[E] Pop-up:** Beim Kind erscheint bei Freischaltung ein Pop-up mit festlicher Grafik und einem Formularfeld für den Wunsch.
- **[E] Begleitung:** Im Pop-up wählt das Kind Mama, Papa oder "egal" als Begleitung. Der Wunsch geht sofort an beide Eltern. (E27)
- **[E] Annahme:** Ein Elternteil bestätigt mit "Wunsch angenommen". Dieser Elternteil ist die Begleitung und kann sie übergeben. Das Kind sieht die Bestätigung in der App.
- **[E]** Der Termin wird außerhalb der App direkt mit dem Kind abgesprochen. Die App hat keine Terminverwaltung.
- **[E]** Die Eltern sehen, wann jedes Kind zuletzt einen Sondertag hatte und mit welchem Elternteil. Der Eintrag ist editierbar. (E27)
- **[V]** Das Kind sieht den Fortschritt (z. B. "Noch 2 Mods und 3 Wochen bis zum Sondertag").

---

## 11. Avatar und Mods

### 11.1 Konzept

- **[E] Stil:** Jedes Kind hat eine eigene Figur in blockiger Optik, orientiert am Stil von Minecraft, weil die Kinder das Spiel mögen.
- **[E] Nichts wird kopiert:** keine Namen, Figuren, Texturen, Bilder oder sonstigen Inhalte aus Minecraft. Alle Grafiken sind eigene Entwürfe. Das gilt auch für andere Marken und Spielfiguren.
- **[E]** Jedes Kind wählt eine Figur und ein Thema.
- **[E] Zehn Themen:** Ritter, Weltraum-Forscher, Ninja, Roboter, Pirat, Wikinger, Fußballer, Basketballer, Rennfahrer, Entdecker im Dschungel oder Wald.
- **[E] Sechs Slots:** Kopf/Helm, Körper/Rüstung, Rücken (z. B. Umhang, Flügel, Jetpack), Hand (Werkzeug oder Waffe, bei Sportthemen z. B. Ball), Begleiter, Hintergrund. (E9)
- **[V]** Sportthemen erhalten passende Mods wie Trikot, Schuhe, Pokal und Stadion als Hintergrund.
- **[E]** Mods sind rein kosmetisch. Sie wirken nicht auf Punkte oder Regeln. Die Kinder bezahlen sie mit Guthaben.
- **[E] Themenwechsel:** jederzeit möglich. Das Kind behält seinen Rang. Die Mods in den Slots gehen verloren, das Kind startet mit leeren Slots. Die Ausbaustufe fällt auf 0 (berechnet aus den aktuellen Slots, keine Sonderregel). Bereits verdiente Sondertage bleiben. (E5)
- **[E] Warnung vor dem Wechsel:** Ein Dialog nennt konkrete Zahlen (verlorene Mods und Punkte, nötige Mods bis zur Ausbaustufe) und verlangt eine Bestätigung. Es gibt keine Erstattung. (E5)
- **[E] Familien-Sicht:** Kinder sehen im Familien-Ranking die Avatare der Brüder mit den erarbeiteten Mods. (E25)
- **[E] Eltern-Avatar:** einfache Blockfigur, gleicher Generator, ohne Mods, Punkte und Rang. Sichtbar im Familien-Dashboard und bei Bestätigungen und Nachrichten. (E10)

### 11.2 Umfang und Seltenheit

- **[E] Seltenheit = Rang:** Die Mod-Seltenheit entspricht den Rangstufen. Ein Mod der Stufe X ist erst ab Rang X kaufbar. (E7, E9)
- **[E] Preise steigen mit der Seltenheit.** Startwerte siehe 18.
- **[E] Umfang pro Thema:** 6 Slots mal 6 Seltenheitsstufen = 36 Mods. Pro Slot und Seltenheit genau ein Mod. (E9)
- **[E] Ausbaustufe:** Anzahl fertig gebauter Mods im aktuellen Rang. Jeder Rang hat 6 Ausbaustufen. (E9)
- **[E] God Mode:** ein Mod pro Slot, z. B. mit goldener Aura oder Animation. Danach neues Mod-Set alle 26 aktiven Wochen (E1). Umfang offen, siehe 19.
- **[V] Datensatz eines Mods:** Name, Thema, Slot, Seltenheit/Rang, Preis, Bauzeit, Grafik.
- **[E] Die Eltern ändern Mods und Preise und ergänzen neue.** Neue Themen und Mods sind reine Daten, keine Codeänderung. (E9)

### 11.3 Grafik

- **[E] Generator:** Die Grafiken entstehen aus gemeinsamen Blockteilen. Pro Thema werden sie umgefärbt und abgewandelt. Einzelne Mods lassen sich von Hand nachbessern. (E9)
- **[V]** Bei 10 Themen mal 36 Mods sind es rund 360 Grafiken. Der Generator setzt pro Slot SVG-Ebenen zusammen.
- **[E]** Eigene Gestaltung, keine Spielinhalte. (Konzept 7.1)

### 11.4 Bauzeit

- **[E] Zeitbremse:** Mods sollen nicht beliebig schnell gekauft und genutzt werden.
- **[V]** Ein gekaufter Mod hat eine Bauzeit: Startwert 2 Tage für Common bis 7 Tage für Legendary. Inszenierung passend zum Thema (Schmiede, Werkstatt o. Ä.). Zwischenwerte siehe 18 und 19.
- **[V]** Ein gekaufter Mod zählt erst nach Fertigstellung für die Ausbaustufe.
- **[V]** Pro Woche zählt höchstens ein fertiger Mod für die Ausbaustufe. Kosmetische Zusatzkäufe sind weiter möglich.

---

### 11.5 Ruhmeshalle (Phase 3)

- **Freischaltung:** Ausbaustufe im aktuellen Rang erreicht die Einstellung `avatar.ruhmeshalle_ausbaustufe` (Standard 6 = alle Slots). Dann kann das Kind seinen Helden **in die Ruhmeshalle stellen** (Bestätigungsdialog, danach neues Thema wählen). Gesperrt, solange im aktuellen Thema noch Bauaufträge laufen (klare Meldung mit Anzahl), damit kein Mod nach dem Einfrieren im alten Thema fertig wird.
- **Nichts geht verloren:** Der Held bleibt mit Thema, Mods, Figur, Rang und Datum für immer erhalten (unveränderlich). Der Avatar beginnt im neuen Thema mit leeren Slots und Ausbaustufe 0. Rang, Punkte, Abzeichen und verdiente Sondertage bleiben; es gibt keinen Verlust-Hinweis (anders als beim normalen Themenwechsel, bei dem Mods verfallen).
- **Darstellung:** Seite "Meine Ruhmeshalle", Kachel für Kinder und Eltern, Tablet-Kachel "N Helden in der Ruhmeshalle". Die Figur steht auf einem Sockel in der Seltenheitsfarbe ihres Rangs; darunter Thema, Rang, Bauzeit in Wochen, Anzahl Mods, bestätigte Aufgaben im Zeitraum und die Widmung.
- **Widmung:** Eltern können je Held einen Text (höchstens 140 Zeichen) schreiben oder ändern (Audit).
- **Abzeichen:** *Erster Held* (1 Held), *Heldentrio* (3), *Sammler* (alle 10 Themen), *Legende* (Held auf höchstem Rang).
- **Benachrichtigung:** Kind-Pop-up und Eltern-Info.

## 12. Dashboards

### 12.1 Kinder-Dashboard

- **[E] Ranking-Dashboard für die Familie** (siehe 8.2). Kinder sehen, wie ihre Brüder stehen, und welche Mods und Zusatzausrüstung sie erarbeitet haben. (Konzept 8.1)
- **[V] Inhalt:**
  - eigenes Avatar
  - Guthaben
  - Rang und Fortschritt
  - Serie und Abzeichen
  - Pause-Hinweis "Pause – deine Serie ist sicher" (E3)
  - offene Aufgaben (auswählbar) mit Reservierungsstatus (E22)
  - Belohnungskatalog mit Einlöseantrag
  - Mod-Shop
  - Familien-Ranking
  - Familienziel-Fortschritt (E26)
  - Pop-ups bei Rangaufstieg, Abzeichen und Sondertag
  - Sondertag-Fortschritt
- **[E] Bedienung für alle Altersstufen:** große Schaltflächen, Symbol zusätzlich zum Text. (E11)
- **[E] Stil (E11):**
  - modernes, dunkles Design (hell optional)
  - Pixelschrift nur für Überschriften, Punkte und Ränge
  - gut lesbare Fließtextschrift (Beispiel: Inter)
  - Schriften selbst gehostet
  - Seltenheitsfarben für die Ränge
  - gleiche Basis für alle Kinder, ohne altersspezifische Varianten
  - jedes Kind wählt eigene Akzentfarbe(n)

### 12.2 Eltern-Dashboard

- **[E]** Passwortgeschützt, getrennt von der Kinderansicht.
- **[E] Stil:** gleiches Designsystem, ruhig und hell. (E11)
- **[E] Inhalte:**
  - Aufgaben anlegen und verwalten, Wochenplanung per Drag-and-Drop
  - Aufgabenbibliothek und Kategorien pflegen
  - offene Meldungen: erledigte Aufgaben bestätigen, Reservierungen entscheiden, Einlöseanträge bestätigen oder ablehnen, Sondertag-Wünsche annehmen
  - nicht übernommene Aufgaben einsehen (5.6)
  - Bonuspunkte vergeben
  - Kinderübersicht: Arbeit, Punktestand, Rang, Serie, Avatar mit Mods
  - Belohnungskatalog, Preise, Limits, Ränge, Schwellen und Mods pflegen
  - Pausen setzen (7)
  - Familienziel und Familienbelohnungen pflegen (8.1)
  - Ranking-Ansicht umschalten (8.2)
  - Sondertag-Historie je Kind mit Begleitung (10)
  - Benachrichtigungen je Elternteil einstellen (13)
  - Protokoll: wer hat was wann getan
  - Prognose und Kalibrierung (6.2)
  - alle Startwerte und Regeln (18)

---

## 13. Benachrichtigungen

- **[E] Sofort:** Die Eltern werden bei jedem Ereignis der Kinder sofort informiert, damit sie jederzeit den Überblick haben. Standard: beide Eltern, Push und E-Mail. (Konzept 9, E24)
- **[E] Ereignisse aus dem Konzept:** Kind wählt eine Aufgabe, meldet sie als erledigt, sendet einen Nachweis, stellt einen Einlöseantrag, schickt einen Sondertag-Wunsch.
- **[E] Weitere Ereignisse aus den Entscheidungen:**
  - Reservierung läuft bald ab: Kind, 6 Stunden vorher (E22)
  - Reservierung abgelaufen: Eltern (E22)
  - Aufgabe "nicht übernommen": Eltern, 3 Stunden vor Ablauf (E23)
  - Familienziel erreicht: Eltern (E26)
  - "Aufgabe bestätigt", "Mod fertig": Kinder-iPhones (E17)
- **[E] Kanäle ab Version 1:** E-Mail und Push auf das iPhone. Keine Sammel-Zusammenfassungen.
- **[E] Konfiguration pro Elternteil:** Jeder Elternteil stellt je Ereignistyp und Kanal ein. (E24)
- **[E] Ruhezeiten pro Elternteil:** Push bleibt stumm, das Ereignis steht trotzdem in der Liste. (E24)
- **[E] Push-Aktionen** wie "Bestätigen", wo die Plattform es unterstützt. (E24)
- **[E]** Im Dashboard sind alle Ereignisse als Liste mit Zähler sichtbar.
- **[E]** Später: Home Assistant als weiterer Kanal. Die App soll weitere Kanäle nachrüsten können. (E24)
- **[E] Mailversand:** eigenes Postfach auf einer eigenen Domain, vom Nutzer eingerichtet. SMTP-Daten im Einrichtungs-Assistenten. (E18)
- **[V] Web-Push auf dem iPhone, Voraussetzungen:**
  - iOS oder iPadOS 16.4 oder neuer
  - Die Seite liegt als Web-App auf dem Home-Bildschirm, mit Web-App-Manifest und `display` auf `standalone` oder `fullscreen`
  - HTTPS
  - Die Berechtigungsabfrage erscheint nur nach einer Nutzeraktion, z. B. Tipp auf "Benachrichtigungen aktivieren". In einem normalen Safari-Tab ist keine Anfrage möglich.
  - Der Server muss ausgehend den Apple-Push-Dienst erreichen (`*.push.apple.com`), falls Firewall oder Proxy ausgehenden Verkehr einschränken.
- **[V] Hinweis:** Die Voraussetzungen haben sich für neuere iOS-Versionen teils geändert (laut OneSignal öffnet das Symbol ab iOS 26 standardmäßig als Web-App). Vor der Umsetzung aktuelle Apple-Dokumentation prüfen.
- **[V] Quellen:**
  - WebKit Blog: "Web Push for Web Apps on iOS and iPadOS", https://webkit.org/?p=13878 (Stand iOS 16.4 Beta 1)
  - OneSignal Dokumentation: "Web Push for iOS", https://documentation.onesignal.com/docs/en/web-push-for-ios

---

## 14. Datenschutz und Betrieb

- **[E] Nachweise:** Fotos und Textnachrichten werden bei Bestätigung sofort gelöscht (siehe 5.4). Im Protokoll bleibt nur der Vermerk.
- **[V]** Fotos liegen nur temporär im Dateisystem des Servers.
- **[V]** Alle Daten bleiben auf dem eigenen Server.
- **[V]** Keine externen Dienste für Analyse oder Tracking.
- **[E]** Schriften werden selbst gehostet. (E11)
- **[E] Backup:** Proxmox-VM-Backup plus tägliche Datenbank-Dumps. (E21)
- **[V]** Wiederherstellungstest durchführen.
- **[E] Zugriff:** Kinder nur im Heimnetz. Eltern erreichen die App unterwegs über das bestehende VPN. (E2, E20)
- **[E] Fernzugriff** (z. B. Tailscale) richtet der Nutzer selbst ein. Das ist nicht Teil des Projekts. (E20)
- **[E] Keine offenen Ports.** Kein Zugriff aus dem Internet ohne VPN. Kein cloudflared für Nestwerk. (E19, E20)

---

## 15. Ausbaustufen

Alle Stufen sind **[V]** und anpassbar. Die Zuordnung der neuen Punkte ist offen (siehe 19).

1. **Kern:**
   - Rollen und Anmeldung, Einrichtungs-Assistent
   - Aufgaben mit Formularfeldern und Wiederholung
   - Aufgabenbibliothek mit Startvorlagen
   - Wochenplanung per Drag-and-Drop
   - Auswahl, Reservierung mit Ablauf, Verfall
   - Erledigungsmeldung mit Nachweis und Bestätigung
   - Bonuspunkte, Ledger und Protokoll
   - Belohnungskatalog mit Einlöseanträgen und Taschengeld-Limit
   - Benachrichtigung per E-Mail und Push mit Einstellungen
   - Kinder- und Eltern-Dashboard in einfacher Form
   - Kiosk-Tablet-Ansicht
2. **Spielebene:**
   - Ränge mit Schwellen und aktiven Wochen
   - Serie, Serienbonus, Pause-Schalter (ersetzt Joker)
   - Abzeichen
   - Avatar-Figur, Themen, Slots, Mods mit Bauzeit, Mod-Shop
   - Familienziel und Familien-Ranking
   - Sondertag mit Pop-up, Wunsch, Begleitung und Abstandsregel
3. **Feinschliff:**
   - Prognose und Kalibrierung
   - Pop-ups und Animationen
   - weitere Themen und Mods
4. **Später:**
   - Lernsystem (eigenes Modul `lernen`, Lernassistent). Anforderungen offen (siehe 19).
   - Forschungssystem (eigenes Modul `forschen`)
   - Home-Assistant-Anbindung (Benachrichtigungskanal, Pause-Automatik, Tablet als Familien-Display)
   - weitere Familienfunktionen

---

## 16. Technik

Die Technik-Empfehlungen des Konzepts (Abschnitt 12) waren unverbindlich. Entschieden ist der Stack unten.

- **[E] Sprache und Framework:** Python 3 mit Django statt Flask. Django bringt Authentifizierung und Admin-Oberfläche mit. (E6)
- **[E] Modulstruktur:** je Funktion eine Django-App (`aufgaben`, `belohnung`, `avatar`; später `lernen`, `forschen`). Gemeinsam: Benutzer, Punkte, Benachrichtigungen, Ereignisse, Einstellungen. (E6)
- **[E] Datenbank:** SQLite im WAL-Modus, eine Datei, einfach zu sichern. (E6)
- **[E] Oberfläche:** serverseitig gerenderte Django-Templates, mobil zuerst, HTMX für Interaktion. (E6)
- **[V] Drag-and-Drop:** SortableJS (unterstützt Touch).
- **[E] PWA:** Web-App-Manifest und Service Worker für Home-Bildschirm und Push. (E6)
- **[E] Push:** Web-Push. (E6)
- **[V] Push-Bibliothek:** Web-Push mit VAPID-Schlüsseln, z. B. `pywebpush`.
- **[V] E-Mail:** `smtplib` oder ein SMTP-Dienst. Zugangsdaten über den Einrichtungs-Assistenten. (E18)
- **[E] Zeitsteuerung:** ein Scheduler-Container ruft Django-Management-Commands auf (E21). Ersetzt die im Konzept genannten APScheduler und systemd-Timer (E6).
  - Aufgaben: wiederkehrende Aufgaben erzeugen, Wochenauswertung (Serie, Familienziel), Bauzeiten, Quartalswechsel (Abzeichen), Verfall und Reservierungsablauf.
- **[E] Idempotenz:** Alle Auswertungen sind idempotent. Ein Neustart erzeugt nichts doppelt. (Konzept 12, E21)
- **[V] Gunicorn** als WSGI-Server im Web-Container.
- **[V] Sicherheit:** gehashte Passwörter und PINs (z. B. Argon2; Django bringt eigene Hasher mit), CSRF-Schutz, Rate-Limit für PIN-Eingaben, Datei-Upload nur für Bilder mit Größenbegrenzung.
- **[V] Tests mit pytest:** Punkte-Ledger, Rangaufstieg, Serie, Abstandsregel, Reservierungen. Ergänzt um Pause, Serienbonus, Verfall und Familienziel. Diese Regeln sind der Kern und sollen automatisiert prüfbar sein.
- **[V] Grafik:** Avatar-Generator, der SVG-Ebenen pro Slot aus Blockteilen zusammensetzt (siehe 11.3).
- **[E] Konfigurierbarkeit:** Alle einstellbaren Werte liegen in der Datenbank (Grundregel 0).

### 16.1 Datenmodell

- **[V] Konzept-Entwurf:** Benutzer (Rolle), Aufgaben, Aufgabenpläne, Aufgaben-Instanzen, Reservierungen und Meldungen, Ledger, Belohnungen, Anträge, Ränge, Mods, gekaufte Mods, Avatare, Themen, Serien, Abzeichen, Sondertage und Wünsche, Benachrichtigungen, Audit-Log, Einstellungen.
- **[E] Ergänzt durch Entscheidungen:** Pausen (Zeiträume), Familienziel und Familienbelohnungen, Aufgabenbibliothek, Kategorien, Benachrichtigungs-Einstellungen je Elternteil, Begleitung je Sondertag, Serienbonus als Ledger-Eintrag, generische Meilenstein- und Abzeichen-Regeln.

### 16.2 Umsetzungsschritte

Konzept-Liste (Abschnitt 14), angepasst. Neue Punkte sind mit (neu) markiert.

1. [V] Dokument prüfen, Annahmen zusammenfassen, Rückfragen zu den offenen Punkten stellen (siehe 19).
2. [V] Projektstruktur anlegen, Technik festlegen (Django, Docker Compose).
3. [V] Datenmodell mit Ledger und Audit-Log umsetzen.
4. [V] Anmeldung: Eltern-Passwort mit Namensangabe, Kinder-PIN, Rate-Limit.
5. [E] Einrichtungs-Assistent mit Startwerten (neu).
6. [V] Aufgaben: Formular mit optionalen Feldern, Wiederholung, Zuweisung, Limit, Status, Kategorie.
7. [V] Aufgabenbibliothek mit Startvorlagen (neu).
8. [V] Wochenplanung per Drag-and-Drop mit Touch-Unterstützung.
9. [V] Automatische Erzeugung wiederkehrender Aufgaben (idempotent), Verfall nicht übernommener Aufgaben (neu).
10. [V] Kinderablauf: Auswahl, Reservierung mit Ablauf (neu), Entscheidung durch Eltern, Erledigungsmeldung, Nachweis, Bestätigung, sofortiges Löschen der Nachweise.
11. [V] Bonuspunkte mit Begründung.
12. [V] Belohnungskatalog, Einlöseanträge, Abbuchung bei Bestätigung, offene Anträge gegen Guthaben rechnen, monatliches Taschengeld-Limit.
13. [V] Benachrichtigungen per E-Mail und Web-Push, Einstellungen je Elternteil (neu), Event-Liste im Dashboard.
14. [V] PWA: Manifest, Service Worker, Push-Aktivierung per Schaltfläche, HTTPS-Betrieb.
15. [V] Ränge, Mindestwochen, Serie, Serienbonus, Pause-Schalter (neu), Abzeichen.
16. [V] Familienziel und Familien-Ranking (neu).
17. [V] Avatar-Generator, Themen, Slots, Mod-Shop mit Bauzeit, Themenwechsel mit Warnung.
18. [V] Sondertag mit Pop-up, Wunsch, Begleitung, Bestätigung und Abstandsregel.
19. [V] Kiosk-Tablet-Ansicht und iPhone-PWA für Kinder (neu).
20. [V] Familien-Ranking und Eltern-Kinderübersicht.
21. [V] Prognose und Kalibrierung.
22. [V] Tests für Ledger, Rang, Serie, Abstandsregel, Reservierung, Pause, Verfall (ergänzt).
23. [V] Deployment: Docker Compose, Reverse-Proxy-Konfiguration, Backup, README mit Einrichtung (statt LXC und systemd).

---

## 17. Deployment (neu)

- **[E] Ziel:** Debian-13-VM auf Proxmox, 2 vCPU, 2 GB RAM, 20 GB Speicher. Betrieb mit Docker Compose. Ersetzt LXC und systemd aus dem Konzept. (E21)
- **[E] Kein Hosting extern.** Kein Hostinger-VPS. Nur der Proxmox-Server zu Hause. (E2)
- **[E] Container:**
  - Web (Django)
  - Scheduler (Management-Commands, idempotent)
  - weitere Module als zusätzliche Container (E21)
- **[E] Datenbank:** SQLite-Datei im Volume, WAL-Modus. (E6)
- **[E] Code:** Git-Repository. Entwicklung in einem lokalen Repository. (E21)
- **[E] Reverse Proxy:** Nginx Proxy Manager. Traefik entfällt. (E19)
- **[E] DNS:** AdGuard-DNS-Eintrag `nestwerk.<Domain>` zeigt im Heimnetz auf den Nginx Proxy Manager. (E19)
- **[E] HTTPS:** Let's-Encrypt-Zertifikat über DNS-Challenge im Nginx Proxy Manager. DNS-Anbieter offen (siehe 19). (E19)
- **[E] Keine offenen Ports.** Kein cloudflared für Nestwerk. (E19, E20)
- **[E] Updates und Rollback** über Container-Versionen. (E21)
- **[E] Backup:** Proxmox-VM-Backup plus tägliche Datenbank-Dumps (siehe 14). (E21)
- **[E] Erweiterbarkeit:** Module als eigene Container. GPU-Durchreichung ist für spätere lokale KI vorgesehen. (E21)

---

## 18. Startwerte

### 18.1 Ränge

| Rang | Gesamtpunkte (XP) ab | Min. aktive Wochen | Mod-Preis je Mod | Bauzeit |
|---|---|---|---|---|
| 1 Common | 0 | 0 | 40 | 2 Tage |
| 2 Uncommon | 2.000 | 20 | 60 | [O] |
| 3 Rare | 5.000 | 42 | 90 | [O] |
| 4 Epic | 9.000 | 64 | 130 | [O] |
| 5 Legendary | 14.000 | 90 | 180 | 7 Tage |
| 6 God Mode | 20.000 | 120 | 250 | [O] |

- **[E]** Schwellen, Mindestwochen und Mod-Preise (E14). Annahme: 150–200 Punkte pro Woche, nach 4–6 Wochen kalibrieren.
- **[V]** Bauzeiten für Common und Legendary (Konzept 7.3). Zwischenwerte offen (siehe 19).

### 18.2 Serienbonus

| Serie (Wochen in Folge) | Bonus |
|---|---|
| 1 | 0 % |
| 2 | +5 % |
| 3 | +10 % |
| 4 | +15 % |
| 5 | +20 % |
| 6 und mehr | +25 % (Deckel) |

- **[E]** Schritt 5 %, Deckel 25 %, Start ab Serie 2. Aufrundung auf ganze Punkte. Buchung sofort pro Aufgabe als Ledger-Eintrag "Serienbonus". (E4)

### 18.3 Abzeichen

| Art | Schwellen |
|---|---|
| Tagesserie | 7, 14, 30 Tage |
| Wochenserie | 1, 2, 4, 8, 12, 24, 48 Wochen |
| Quartal | Quartal mit durchgehend aktiven Wochen |
| Rangaufstieg | ein Abzeichen je Aufstieg |

- **[E]** Abzeichen geben keine Punkte. (E12)
- **[O]** Gestaltung der Abzeichen (siehe 19).

### 18.4 Belohnungskatalog

| Eintrag | Kategorie | Preis (Punkte) |
|---|---|---|
| Süßes klein | Süßes | 15 |
| Süßes groß | Süßes | 30 |
| 30 Min. Fernsehzeit | Fernsehzeit | 30 |
| 30 Min. Gaming oder Computerzeit | Gaming- und Computerzeit | 45 |
| 1 € Taschengeld | Taschengeld | 30 |

- **[E]** Taschengeld-Limit: 10 € pro Monat und Kind. (E13)

### 18.5 Aufgabenbibliothek

| Vorlage | Punkte | Freigabe |
|---|---|---|
| Müll rausbringen | 5 | Vertrauen |
| Mülltonnen rausstellen | 10 | Vertrauen |
| Leergut wegbringen | 15 | Vertrauen |
| Altglas | 15 | Vertrauen |
| Spülmaschine ausräumen | 10 | Vertrauen |
| Spülmaschine einräumen | 10 | Vertrauen |
| Tisch decken und abräumen | 10 | Vertrauen |
| Einkaufsliste | 10 | Eltern |
| Wäsche waschen | 15 | Eltern |
| Wäsche aufhängen | 15 | Eltern |
| Wäsche zusammenlegen und einräumen | 20 | Eltern |
| Flur saugen | 15 | Eltern |
| Vokabeln lernen (15 Min.) | 15 | Eltern |
| Zimmer gründlich aufräumen | 30 | Foto |
| Bad putzen | 40 | Foto |
| Rasen mähen | 45 | Foto |
| Auto aussaugen | 30 | Foto |

- **[E]** Startvorlagen (E15). Eltern können jederzeit ergänzen, ändern und löschen.

### 18.6 Familienziel

| Wert | Startwert |
|---|---|
| Wochenziel | 450 Punkte (verdiente XP aller Kinder, Montag bis Sonntag) |
| Bedingung | Jedes nicht pausierte Kind hat mindestens eine bestätigte Aufgabe |
| Großziel | nach 4 Wochenzielen in Folge (Beispiel: Ausflug) |
| Familienbelohnungen (Startliste) | Pizza, Spieleabend, Kino, Eis, Grillen |
| Abstimmung | Kinder sonntags für die Folgewoche, bei Gleichstand die Eltern |

- **[E]** Alle Werte einstellbar (E26).

### 18.7 Sondertage

| Regel | Wert |
|---|---|
| Meilenstein | Ausbaustufe 6 in Rang 2, 3, 4 und 5, je einmal |
| God Mode | danach alle 26 aktiven Wochen, endlos, mit neuem Mod-Set |
| Maximum | 2 pro Kind und App-Jahr |
| App-Jahr | beginnt am Go-live-Datum |
| Mindestabstand | 150 Tage |
| Bezugsdatum Abstand | Datum der Annahme, korrigierbar [V] |

- **[E]** Alle Werte sind Regeln in der Datenbank (E1).

### 18.8 Reservierung und Verfall

| Regel | Wert |
|---|---|
| Ablauf ungebundene Aufgabe | 48 Stunden |
| Ablauf zeitgebundene Aufgabe | zur Frist |
| Erinnerung an das Kind | 6 Stunden vor Ablauf |
| Push an die Eltern bei "nicht übernommen" | 3 Stunden vor Ablauf |
| Strafe | keine |

- **[E]** (E22, E23)

### 18.9 Weitere Werte

| Wert | Startwert | Status |
|---|---|---|
| Richtwert Punkte | 1 Punkt ca. 1 Minute Aufwand | [E] |
| Wochenbeginn | Montag | [E] |
| Auto-Logout Kinder-Tablet | ca. 5 Minuten Inaktivität | [E] |
| Sonderpunkte-Obergrenze | 50 % des Aufgabenwerts, abschaltbar | [V] |
| Mod-Zählung für die Ausbaustufe | höchstens 1 fertiger Mod pro Woche | [V] |
| Kalibrierung | nach 4–6 Wochen, Faktor pro Kind | [E] |
| Sprache | Deutsch | [V] |
| Zeitzone | Europe/Berlin | [O] |
| PIN-Sperre (Fehlversuche, Dauer) | nicht festgelegt | [O] |
| Maximale Bildgröße für Nachweise | nicht festgelegt | [O] |

---

## 19. Offene Punkte

1. **[O] Zeitzone** bestätigen. Standard: Europe/Berlin.
2. **[O] Gestaltung der Abzeichen** (Symbole, Look).
3. **[O] God Mode:** Umfang und Preise des neuen Mod-Sets nach 26 Wochen. Gilt der Meilenstein "Ausbaustufe 6 in God Mode" zusätzlich zum 26-Wochen-Zyklus?
4. **[O] Bauzeiten** für Uncommon bis Epic und God Mode. Das Konzept nennt nur 2 Tage (Common) und 7 Tage (Legendary).
5. **[O] Bezugswoche Serienbonus:** laufende oder vorherige, abgeschlossene Woche?
6. **[O] Ranking-Modi:** Welche Ansichten sind im Eltern-Dashboard umschaltbar (Showcase, "Held der Woche", Rohpunkte)? Entscheidung 25 nennt nur "umschaltbar".
7. **[O] DNS-Anbieter** für die Let's-Encrypt-DNS-Challenge. Entscheidung 19 nennt "vermutlich Cloudflare".
8. **[O] Stufenzuordnung neuer Punkte.** Vorschlag: Assistent, Kiosk-Tablet, Aufgabenbibliothek und Taschengeld-Limit in Kern. Pause, Familienziel, Ranking in Spielebene.
9. **[O] Lernsystem:** Anforderungen an Lernassistent (eigenes Interview, Konzept 13.12).
10. **[O] Home-Assistant-Anbindung:** Anforderungen (eigenes Interview).
11. **[O] Technische Standardwerte:** PIN-Sperre (Anzahl Fehlversuche, Dauer) und maximale Bildgröße für Nachweise. Standard setzen und kennzeichnen.

---

## 20. Änderungen gegenüber dem Ursprungskonzept

- **Joker** entfällt. Ersetzt durch den Pause-Schalter (E3).
- **Sondertage:** Statt Rang 2–4 und Kalenderjahr jetzt Ausbaustufe 6 in Rang 2–5, App-Jahr ab Go-live (E1).
- **God Mode:** Nicht mehr ohne Belohnung. Sondertag und neues Mod-Set alle 26 aktiven Wochen (E1).
- **Mindestabstand:** 5 Monate werden zu 150 Tagen (E1).
- **Flask** wird zu **Django** (E6). HTMX statt "HTMX oder Alpine.js" (E6).
- **LXC und systemd** werden zu **Debian-VM mit Docker Compose** (E21). Hostinger-VPS entfällt (E2).
- **systemd-Timer** (E6) werden durch den **Scheduler-Container** ersetzt (E21).
- **Traefik-Option** entfällt. Nginx Proxy Manager (E19).
- **Fernzugriff:** kein HTTPS von außen, nur VPN. Einrichtung durch den Nutzer (E2, E19, E20).
- **Kinder-Sitzungen:** Tablet mit Auto-Logout nach ca. 5 Minuten, eigene iPhones bleiben angemeldet (E17).
- **Benachrichtigungen:** "jedes Ereignis sofort" bleibt Standard, ist aber pro Elternteil einstellbar (E24).
- **Serienbonus:** sofort pro Aufgabe statt auf die Wochensumme (E4).
- **Meilensteine erweitert:** Tagesserie 30, Wochenserie 1, 2, 24, 48, Abzeichen je Rangaufstieg (E12).
- **Reservierung:** Ablauf nach Frist oder 48 Stunden, Erinnerung 6 Stunden vorher (E22). Verfall nicht übernommener Aufgaben ist neu (E23).
- **Familienziel:** Gemeinschaftsziel ohne individuelle Wochenvorgabe (E26).
- **Konfiguration:** Namen, PINs, Passwort, SMTP und Startwerte über den Einrichtungs-Assistenten statt Konzept-[O] (E7).
- **Geschlossene Konzept-[O]-Punkte:** App-Name Nestwerk (E8), Stil der Kinderoberfläche (E11), Startwerte für Ränge, Katalog und Bibliothek (E13–E15), Mod-Seltenheit an Rang gekoppelt und 36 Mods pro Thema (E7, E9), Eltern-Avatar (E10), Meilenstein-Schwellen (E12), Mailpostfach (E18).
- **Stufen:** Aufgabenbibliothek und Taschengeld-Limit nach Kern verschoben, weil die Startwerte im Assistenten gebraucht werden (E13, E15). Zuordnung offen (siehe 19, Punkt 8).
- **Module:** Lernsystem und Forschungssystem als eigene Django-Module (Vorgabe des Auftrags).
