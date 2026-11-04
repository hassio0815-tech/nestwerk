"""Erklärkarten je Rechenart (SPEC 21.13, Etappe 10b): Merksatz in drei Sprachstufen und ein festes
Mini-Beispiel mit eigenen Zahlen.

Die Sprachstufen folgen ``texte.py``: Stufe 1 bis Klasse 4, Stufe 2 Klasse 5 bis 7, Stufe 3
ab Klasse 8. Alle Texte sind Daten (``gettext_noop``, DE als msgid) und werden erst beim Anzeigen
übersetzt. Karten sind reine Erklärungen: Sie lösen nie eine echte Aufgabe. Zeigt eine Karte
zufällig die Lösung der gerade offenen Aufgabe (z. B. ``1 m = 100 cm``), blendet die Anzeige sie
dort aus.
"""

from dataclasses import dataclass

from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop

STUFE_MAX = 3


@dataclass(frozen=True)
class Karte:
    schluessel: str
    titel: str  # msgid
    stufen: tuple  # drei msgids
    beispiel: str  # msgid


@dataclass(frozen=True)
class KartenText:
    schluessel: str
    titel: str
    merksatz: str
    beispiel: str


KARTEN = {
    k.schluessel: k
    for k in (
        Karte(
            "add_sub",
            gettext_noop("Plus und Minus"),
            (
                gettext_noop(
                    "Rechne von rechts nach links: erst die Einer, dann die Zehner. Wird eine "
                    "Stelle zweistellig, schreibst du die Einer hin und merkst dir die Zehner als "
                    "Übertrag. Beim Minus holst du dir bei Bedarf einen Zehner von der "
                    "Nachbarstelle."
                ),
                gettext_noop(
                    "Schriftlich rechnest du Stelle für Stelle von rechts nach links. Beim Plus "
                    "gibt es einen Übertrag, wenn eine Stelle zweistellig wird. Beim Minus "
                    "entbündelst du, wenn die obere Ziffer kleiner ist als die untere."
                ),
                gettext_noop(
                    "Addiere und subtrahiere stellenweise von rechts. Überträge gehören zur "
                    "nächsten Stelle, beim Subtrahieren wird links entbündelt. Mit der "
                    "Umkehraufgabe prüfst du das Ergebnis."
                ),
            ),
            gettext_noop(
                "47 + 38: Einer 7 + 8 = 15, schreibe 5, übertrage 1. Zehner 4 + 3 + 1 = 8. "
                "Ergebnis: 85."
            ),
        ),
        Karte(
            "einmaleins",
            gettext_noop("Kleines Einmaleins"),
            (
                gettext_noop(
                    "Lerne die Reihen auswendig. Kennst du eine Aufgabe nicht, hilft die "
                    "Tauschaufgabe: Es ist egal, welche Zahl vorne steht. Bei Zehnerzahlen "
                    "rechnest du ohne die Nullen und hängst sie am Ende an."
                ),
                gettext_noop(
                    "Das Einmaleins gehört zum sicheren Wissen. Die Tauschaufgabe hat dasselbe "
                    "Ergebnis. Bei Zehnerzahlen rechnest du zuerst ohne Nullen und hängst sie "
                    "danach wieder an."
                ),
                gettext_noop(
                    "Die Multiplikation ist vertauschbar. Bei Faktoren mit Endnullen rechnest du "
                    "ohne Nullen und ergänzt sie im Ergebnis."
                ),
            ),
            gettext_noop(
                "6 · 4 = 24, und die Tauschaufgabe 4 · 6 ist auch 24. Bei 30 · 4 rechnest du 3 · 4 "
                "= 12 und hängst eine Null an: 120."
            ),
        ),
        Karte(
            "umkehr",
            gettext_noop("Umkehraufgaben"),
            (
                gettext_noop(
                    "Plus und Minus gehören zusammen, Mal und Geteilt auch. Fehlt in einer Aufgabe "
                    "eine Zahl, rechnest du die Umkehraufgabe. Mit der Probe prüfst du dein "
                    "Ergebnis."
                ),
                gettext_noop(
                    "Addition und Subtraktion sind Umkehrungen, ebenso Multiplikation und "
                    "Division. Die fehlende Zahl findest du mit der Umkehraufgabe. Die Probe "
                    "zeigt, ob es stimmt."
                ),
                gettext_noop(
                    "Eine fehlende Zahl bestimmst du durch die Umkehroperation. Die Probe durch "
                    "Einsetzen sichert das Ergebnis."
                ),
            ),
            gettext_noop("? · 6 = 42: Umkehraufgabe 42 : 6 = 7. Probe: 7 · 6 = 42."),
        ),
        Karte(
            "division_ohne_rest",
            gettext_noop("Teilen ohne Rest"),
            (
                gettext_noop(
                    "Beim Teilen fragst du: Wie oft passt die kleine Zahl in die große? Die "
                    "Mal-Reihe hilft dir: Die kleine Zahl mal wie viel ergibt die große?"
                ),
                gettext_noop(
                    "Dividieren heißt: Wie oft passt der Teiler in die Zahl? Nutze die Mal-Reihe "
                    "des Teilers und die Umkehraufgabe."
                ),
                gettext_noop(
                    "Die Division ist die Umkehrung der Multiplikation. Suche den Faktor, der mit "
                    "dem Teiler das Produkt ergibt."
                ),
            ),
            gettext_noop(
                "36 : 4 = ? Frage dich: 4 mal wie viel ist 36? 4 · 9 = 36, also 36 : 4 = 9."
            ),
        ),
        Karte(
            "geld",
            gettext_noop("Euro und Cent"),
            (
                gettext_noop(
                    "Ein Euro hat 100 Cent. Von Euro zu Cent rechnest du mal 100, von Cent zu Euro "
                    "geteilt durch 100. Geld schreibst du mit Komma und zwei Stellen."
                ),
                gettext_noop(
                    "1 € sind 100 ct. Euro in Cent: mal 100. Cent in Euro: durch 100 teilen. "
                    "Beträge schreibst du mit zwei Stellen hinter dem Komma."
                ),
                gettext_noop(
                    "1 € = 100 ct. Umrechnen: mal 100 oder geteilt durch 100. Geldbeträge stehen "
                    "mit zwei Nachkommastellen; beim Addieren steht Komma unter Komma."
                ),
            ),
            gettext_noop("3 € 20 ct = 320 ct. Und 450 ct = 4,50 €."),
        ),
        Karte(
            "laenge",
            gettext_noop("Meter und Zentimeter"),
            (
                gettext_noop(
                    "Ein Meter hat 100 Zentimeter, ein Zentimeter hat 10 Millimeter. Zu einer "
                    "kleineren Einheit rechnest du mal, zu einer größeren geteilt."
                ),
                gettext_noop(
                    "1 m = 100 cm und 1 cm = 10 mm. In eine kleinere Einheit rechnest du mit mal, "
                    "in eine größere mit geteilt."
                ),
                gettext_noop(
                    "1 m = 100 cm, 1 cm = 10 mm. Kleinere Einheit: multiplizieren, größere "
                    "Einheit: dividieren."
                ),
            ),
            gettext_noop("6 m 40 cm = 640 cm. 80 mm = 8 cm."),
        ),
        Karte(
            "mult_schriftlich",
            gettext_noop("Schriftlich malnehmen"),
            (
                gettext_noop(
                    "Nimm jede Ziffer der zweiten Zahl einzeln mit der ersten Zahl mal. Wichtig: "
                    "Bei den Zehnern kommt hinten eine Null dazu. Am Schluss zählst du die "
                    "Teilergebnisse zusammen."
                ),
                gettext_noop(
                    "Multipliziere die erste Zahl nacheinander mit jeder Ziffer der zweiten Zahl. "
                    "Jede Stelle weiter links verschiebt das Teilergebnis um eine Stelle. Dann "
                    "addierst du die Teilergebnisse."
                ),
                gettext_noop(
                    "Bilde Teilprodukte mit jeder Ziffer des zweiten Faktors, verschoben um die "
                    "Stelle. Die Summe der Teilprodukte ist das Ergebnis."
                ),
            ),
            gettext_noop("23 · 14: 23 · 4 = 92, 23 · 10 = 230, 92 + 230 = 322."),
        ),
        Karte(
            "div_schriftlich",
            gettext_noop("Schriftlich teilen"),
            (
                gettext_noop(
                    "Teile von links nach rechts. Passt die Zahl nicht hinein, nimmst du die "
                    "nächste Ziffer dazu. Bleibt ein Rest, holst du die nächste Ziffer herunter. "
                    "Bleibt am Ende ein Rest, ist das der Rest."
                ),
                gettext_noop(
                    "Teile Stelle für Stelle von links. Ist der Teiler zu groß, nimmst du die "
                    "nächste Ziffer dazu. Ein Rest wird mit der nächsten Ziffer weitergeführt. Mit "
                    "Komma und Nullen kannst du weiterteilen."
                ),
                gettext_noop(
                    "Schriftliche Division: von links Ziffer für Ziffer teilen, den Rest mit der "
                    "nächsten Ziffer weiterführen. Bleibt ein Rest, setze das Komma und hänge "
                    "Nullen an."
                ),
            ),
            gettext_noop("96 : 4: 9 : 4 = 2 Rest 1. Dann 16 : 4 = 4. Ergebnis: 24."),
        ),
        Karte(
            "bruch_kuerzen",
            gettext_noop("Brüche kürzen"),
            (
                gettext_noop(
                    "Kürzen heißt: Zähler und Nenner durch dieselbe Zahl teilen. Der Bruch hat "
                    "danach den gleichen Wert. Du bist fertig, wenn keine Zahl mehr in beide passt."
                ),
                gettext_noop(
                    "Beim Kürzen teilst du Zähler und Nenner durch dieselbe Zahl. Der Wert bleibt "
                    "gleich. Kürze, bis nur noch die Zahl 1 beide teilt."
                ),
                gettext_noop(
                    "Kürzen: Zähler und Nenner durch einen gemeinsamen Teiler dividieren. Am "
                    "besten durch den größten gemeinsamen Teiler, dann ist der Bruch sofort "
                    "vollständig gekürzt."
                ),
            ),
            gettext_noop("12/18: Teile beide durch 6, das ergibt 2/3."),
        ),
        Karte(
            "bruch_erweitern",
            gettext_noop("Brüche erweitern"),
            (
                gettext_noop(
                    "Erweitern heißt: Zähler und Nenner mit derselben Zahl malnehmen. Der Wert des "
                    "Bruchs bleibt gleich. Finde zuerst heraus, mit welcher Zahl du den Nenner "
                    "malnehmen musst."
                ),
                gettext_noop(
                    "Beim Erweitern multiplizierst du Zähler und Nenner mit derselben Zahl. Die "
                    "Erweiterungszahl findest du, indem du den neuen Nenner durch den alten teilst."
                ),
                gettext_noop(
                    "Erweitern: Zähler und Nenner mit derselben Zahl multiplizieren. "
                    "Erweiterungszahl = neuer Nenner : alter Nenner."
                ),
            ),
            gettext_noop("2/3 = ?/12: 12 : 3 = 4, also 2 · 4 = 8. Es ist 8/12."),
        ),
        Karte(
            "bruch_addsub",
            gettext_noop("Brüche addieren und subtrahieren"),
            (
                gettext_noop(
                    "Haben die Brüche denselben Nenner, rechnest du nur die Zähler. Der Nenner "
                    "bleibt. Sind die Nenner verschieden, machst du sie zuerst gleich, indem du "
                    "erweiterst. Zum Schluss kürzt du."
                ),
                gettext_noop(
                    "Bei gleichem Nenner rechnest du mit den Zählern, der Nenner bleibt. Bei "
                    "verschiedenen Nennern erweiterst du auf den gemeinsamen Nenner. Das Ergebnis "
                    "kürzt du, wenn es geht."
                ),
                gettext_noop(
                    "Bruchaddition und -subtraktion: Gleichnamig machen (kleinstes gemeinsames "
                    "Vielfaches der Nenner), Zähler verrechnen, Nenner beibehalten, vollständig "
                    "kürzen."
                ),
            ),
            gettext_noop("1/4 + 1/6: gemeinsamer Nenner 12. 3/12 + 2/12 = 5/12."),
        ),
        Karte(
            "dezimal_runden",
            gettext_noop("Dezimalzahlen runden"),
            (
                gettext_noop(
                    "Suche die Stelle, auf die du runden sollst. Schau auf die Ziffer gleich "
                    "rechts davon. Ist sie 0 bis 4, rundest du ab. Ist sie 5 bis 9, rundest du auf."
                ),
                gettext_noop(
                    "Runden: Zielstelle suchen, die Ziffer rechts daneben ansehen. Bei 0 bis 4 "
                    "bleibt die Zielstelle, bei 5 bis 9 wird sie um eins größer. Alles dahinter "
                    "fällt weg."
                ),
                gettext_noop(
                    "Gerundet wird an der Zielstelle nach der Ziffer rechts davon: Ziffern 0 bis 4 "
                    "runden ab, 5 bis 9 auf. Folgende Stellen entfallen."
                ),
            ),
            gettext_noop(
                "3,47 auf Zehntel: Die nächste Ziffer ist 7, also wird aufgerundet. Ergebnis: 3,5."
            ),
        ),
        Karte(
            "dezimal_rechnen",
            gettext_noop("Mit Dezimalzahlen rechnen"),
            (
                gettext_noop(
                    "Beim Plus und Minus schreibst du Komma unter Komma. Fehlende Stellen füllst "
                    "du mit Nullen. Beim Malnehmen rechnest du ohne Komma und setzt es am Ende "
                    "wieder."
                ),
                gettext_noop(
                    "Plus und Minus: Komma unter Komma, mit Nullen auffüllen. Mal und Geteilt: "
                    "ohne Komma rechnen, dann das Komma setzen (Stellen zählen)."
                ),
                gettext_noop(
                    "Addition und Subtraktion stellengerecht. Bei Multiplikation Nachkommastellen "
                    "beider Faktoren addieren, bei Division durch eine ganze Zahl das Komma beim "
                    "Überschreiten setzen."
                ),
            ),
            gettext_noop("2,5 + 1,75: Kommas untereinander, 2,50 + 1,75 = 4,25."),
        ),
        Karte(
            "prozent_anteil",
            gettext_noop("Prozent: Anteile"),
            (
                gettext_noop(
                    "Prozent heißt: von Hundert. 50 Prozent sind die Hälfte. Einen Bruch kannst du "
                    "auf den Nenner 100 bringen, dann liest du die Prozent am Zähler ab."
                ),
                gettext_noop(
                    "Prozent bedeutet Hundertstel. Um einen Anteil in Prozent zu schreiben, teilst "
                    "du den Teil durch das Ganze und nimmst mal 100."
                ),
                gettext_noop(
                    "Prozentsatz = Anteil : Ganzes · 100 %. Alternativ den Bruch auf den Nenner "
                    "100 erweitern."
                ),
            ),
            gettext_noop(
                "1/4 = 25/100 = 25 %. Oder: 30 von 120: 30 : 120 = 0,25, mal 100 sind 25 %."
            ),
        ),
        Karte(
            "prozent_wert",
            gettext_noop("Prozent: Prozentwert"),
            (
                gettext_noop(
                    "Zuerst suchst du ein Prozent: Das ist der Grundwert geteilt durch 100. Dann "
                    "nimmst du dieses eine Prozent so oft, wie die Prozentzahl sagt."
                ),
                gettext_noop(
                    "Prozentwert: Grundwert durch 100 ergibt ein Prozent. Das rechnest du mal die "
                    "Prozentzahl."
                ),
                gettext_noop("Prozentwert = Grundwert : 100 · Prozentsatz."),
            ),
            gettext_noop("25 % von 80: 80 : 100 = 0,8 und 0,8 · 25 = 20."),
        ),
        Karte(
            "groessen_umrechnen",
            gettext_noop("Größen umrechnen"),
            (
                gettext_noop(
                    "Zuerst fragst du: Wie viele kleine Einheiten hat die große? Von groß nach "
                    "klein rechnest du mal, von klein nach groß geteilt. Bei Kilogramm, Meter und "
                    "Liter ist der Umrechnungsfaktor 1000, bei den Stunden 60."
                ),
                gettext_noop(
                    "Umrechnungszahlen: 1 km = 1000 m, 1 kg = 1000 g, 1 l = 1000 ml, 1 h = 60 min. "
                    "Groß in klein: mal. Klein in groß: geteilt."
                ),
                gettext_noop(
                    "Zur kleineren Einheit multiplizieren, zur größeren dividieren; die "
                    "Umrechnungszahl steht in der Tabelle der Einheiten (Zeit: 60, sonst "
                    "Zehnerpotenzen)."
                ),
            ),
            gettext_noop("3,5 kg = 3500 g. 2400 ml = 2,4 l."),
        ),
        Karte(
            "punkt_vor_strich",
            gettext_noop("Punkt vor Strich"),
            (
                gettext_noop(
                    "Mal und Geteilt (Punktrechnung) kommen vor Plus und Minus (Strichrechnung). "
                    "Rechne erst die Punktaufgaben aus und dann den Rest von links nach rechts."
                ),
                gettext_noop(
                    "Punkt vor Strich: Zuerst Mal und Geteilt, danach Plus und Minus, jeweils von "
                    "links nach rechts."
                ),
                gettext_noop(
                    "Rangfolge der Rechenarten: Punktrechnung vor Strichrechnung, gleichrangige "
                    "Rechnungen von links nach rechts."
                ),
            ),
            gettext_noop("5 + 3 · 4: erst 3 · 4 = 12, dann 5 + 12 = 17."),
        ),
        Karte(
            "klammern",
            gettext_noop("Klammern und Rechengesetze"),
            (
                gettext_noop(
                    "Was in der Klammer steht, rechnest du zuerst. Manchmal kannst du geschickt "
                    "rechnen: Bei Mal-Aufgaben darfst du die Reihenfolge tauschen, so findest du "
                    "runde Zahlen."
                ),
                gettext_noop(
                    "Klammern zuerst, dann Punkt vor Strich. Vorteilhaft rechnen: Faktoren "
                    "tauschen und passende zusammenfassen oder gleiche Faktoren ausklammern."
                ),
                gettext_noop(
                    "Klammern haben Vorrang. Vorteilhaft rechnen mit Kommutativ-, Assoziativ- und "
                    "Distributivgesetz."
                ),
            ),
            gettext_noop(
                "(6 + 2) · 3: Klammer 8, dann 8 · 3 = 24. Geschickt: 4 · 17 · 25 = 100 · 17 = 1700."
            ),
        ),
        Karte(
            "gleichung_linear",
            gettext_noop("Lineare Gleichungen"),
            (
                gettext_noop(
                    "Du willst x allein auf eine Seite bekommen. Was du auf der einen Seite "
                    "machst, machst du auch auf der anderen. Entferne erst die Zahlen mit Plus und "
                    "Minus, dann teilst du durch die Zahl vor x."
                ),
                gettext_noop(
                    "Eine Gleichung löst du mit Umformen: Auf beiden Seiten dieselbe Rechnung. "
                    "Erst Plus und Minus wegschaffen, dann durch die Zahl vor x teilen. Mach zum "
                    "Schluss die Probe."
                ),
                gettext_noop(
                    "Äquivalenzumformungen auf beiden Seiten: Zuerst Summanden, dann den Faktor "
                    "von x beseitigen; bei Klammern zuerst teilen oder ausmultiplizieren. Mit der "
                    "Probe prüfst du die Lösung."
                ),
            ),
            gettext_noop(
                "2x + 3 = 11: minus 3 ergibt 2x = 8. Durch 2 ergibt x = 4. Probe: 2 · 4 + 3 = 11."
            ),
        ),
        Karte(
            "term_zusammenfassen",
            gettext_noop("Terme zusammenfassen"),
            (
                gettext_noop(
                    "Nur gleiche Buchstaben darfst du zusammenfassen: x mit x, Zahlen mit Zahlen. "
                    "Das Vorzeichen davor gehört zur Zahl."
                ),
                gettext_noop(
                    "Gleichartige Terme fasst du zusammen: Die Zahlen vor demselben Buchstaben "
                    "werden addiert oder subtrahiert. Zahlen ohne Buchstaben bilden eine eigene "
                    "Gruppe."
                ),
                gettext_noop(
                    "Gleichartige Terme (gleiche Variable und Hochzahl) werden durch Addition der "
                    "Koeffizienten zusammengefasst."
                ),
            ),
            gettext_noop("4x + 2 + 3x − 5 = 7x − 3."),
        ),
        Karte(
            "term_ausmultiplizieren",
            gettext_noop("Terme ausmultiplizieren"),
            (
                gettext_noop(
                    "Die Zahl vor der Klammer wird mit jedem Teil in der Klammer malgenommen. "
                    "Achte auf das Vorzeichen. Bei zwei Klammern wird jeder Teil mit jedem Teil "
                    "malgenommen."
                ),
                gettext_noop(
                    "Ausmultiplizieren: Jeder Summand der Klammer wird mit dem Faktor malgenommen. "
                    "Bei zwei Klammern multiplizierst du jeden Summanden der ersten mit jedem der "
                    "zweiten, danach fasst du zusammen."
                ),
                gettext_noop(
                    "Distributivgesetz: a(b + c) = ab + ac. Bei zwei Klammern vier Produkte "
                    "bilden, Vorzeichen beachten, zusammenfassen."
                ),
            ),
            gettext_noop("3(x + 4) = 3x + 12. (x + 2)(x + 5) = x² + 5x + 2x + 10 = x² + 7x + 10."),
        ),
        Karte(
            "prozent_rechnen",
            gettext_noop("Prozentrechnung"),
            (
                gettext_noop(
                    "Grundwert ist das Ganze, Prozentwert ist der Teil, Prozentsatz sind die "
                    "Prozent. Prozentwert = Grundwert : 100 · Prozentsatz. Ein Rabatt macht den "
                    "Preis kleiner, Steuer macht ihn größer."
                ),
                gettext_noop(
                    "Drei Größen: Grundwert (das Ganze), Prozentwert (der Teil) und Prozentsatz. "
                    "Wenn eine fehlt, rechnest du über ein Prozent. Rabatt wird abgezogen, Steuer "
                    "wird dazugerechnet."
                ),
                gettext_noop(
                    "Prozentwert = Grundwert · Prozentsatz. Umstellen nach der gesuchten Größe. "
                    "Verminderter Grundwert: Faktor 1 − p, vermehrter Grundwert: Faktor 1 + p."
                ),
            ),
            gettext_noop("20 % Rabatt auf 60 €: Rabatt 12 €, neuer Preis 48 €."),
        ),
        Karte(
            "zinsen",
            gettext_noop("Zinsrechnung"),
            (
                gettext_noop(
                    "Zinsen sind ein Prozentwert: Das Kapital ist der Grundwert, der Zinssatz die "
                    "Prozentzahl. Für Monate rechnest du erst ein ganzes Jahr und teilst dann "
                    "durch 12. Beim Zinseszins kommen die Zinsen im nächsten Jahr zum Kapital dazu."
                ),
                gettext_noop(
                    "Zinsen = Kapital : 100 · Zinssatz (für ein Jahr). Für Monate: Jahreszinsen : "
                    "12 · Monate. Beim Zinseszins rechnest du Jahr für Jahr mit dem neuen Guthaben."
                ),
                gettext_noop(
                    "Z = K · p/100 für ein Jahr. Für m Monate Z = K · p/100 · m/12. Zinseszins: "
                    "Endkapital = K · (1 + p/100) hoch Jahre."
                ),
            ),
            gettext_noop("800 € bei 3 % im Jahr: 800 : 100 = 8 und 8 · 3 = 24 €."),
        ),
        Karte(
            "dreisatz_proportional",
            gettext_noop("Dreisatz (proportional)"),
            (
                gettext_noop(
                    "Mehr Menge, mehr Preis. Zuerst rechnest du auf eine Einheit herunter, dann "
                    "auf die gewünschte Menge hoch."
                ),
                gettext_noop(
                    "Proportional heißt: doppelte Menge, doppelter Wert. Rechne zuerst auf eine "
                    "Einheit (teilen), dann auf die neue Menge (malnehmen)."
                ),
                gettext_noop(
                    "Proportionaler Dreisatz: Wert je Einheit bestimmen (dividieren), dann mit der "
                    "neuen Menge multiplizieren."
                ),
            ),
            gettext_noop("4 kg kosten 6 €. Ein kg: 6 : 4 = 1,50 €. Dann 7 kg: 1,50 · 7 = 10,50 €."),
        ),
        Karte(
            "dreisatz_antiproportional",
            gettext_noop("Dreisatz (antiproportional)"),
            (
                gettext_noop(
                    "Mehr Helfer, weniger Zeit. Zuerst rechnest du aus, wie viel Arbeit es "
                    "insgesamt ist (mal). Dann verteilst du sie auf die neue Anzahl (geteilt)."
                ),
                gettext_noop(
                    "Antiproportional heißt: doppelte Anzahl, halbe Zeit. Gesamtaufwand = Anzahl "
                    "mal Zeit. Danach teilst du durch die neue Anzahl."
                ),
                gettext_noop(
                    "Antiproportionaler Dreisatz: Das Produkt aus Anzahl und Zeit bleibt gleich. "
                    "Gesamtaufwand berechnen, durch die neue Anzahl teilen."
                ),
            ),
            gettext_noop(
                "3 Arbeiter brauchen 8 Tage. Gesamt: 3 · 8 = 24. Mit 6 Arbeitern: 24 : 6 = 4 Tage."
            ),
        ),
        Karte(
            "potenzen",
            gettext_noop("Potenzen"),
            (
                gettext_noop(
                    "Eine Potenz ist eine Kurzform für eine Mal-Aufgabe mit immer derselben Zahl. "
                    "Die Hochzahl sagt, wie oft die Basis als Faktor da steht. Bei negativer Basis "
                    "in der Klammer zählt das Vorzeichen mit."
                ),
                gettext_noop(
                    "Potenz: Die Basis wird so oft mit sich selbst malgenommen, wie die Hochzahl "
                    "sagt. Das ist etwas anderes als Basis mal Hochzahl. Bei einer negativen Basis "
                    "kommt es auf die Klammer an."
                ),
                gettext_noop(
                    "a hoch n bedeutet n gleiche Faktoren a. Achtung: (−a)² ist positiv, −a² "
                    "negativ. Potenzen werden vor Punkt und Strich berechnet."
                ),
            ),
            gettext_noop("2³ = 2 · 2 · 2 = 8. (−3)² = (−3) · (−3) = 9."),
        ),
        Karte(
            "wurzeln",
            gettext_noop("Wurzeln"),
            (
                gettext_noop(
                    "Die Wurzel fragt: Welche Zahl mit sich selbst malgenommen ergibt diese Zahl? "
                    "Das ist die Umkehrung vom Quadrieren. Lerne die Quadratzahlen."
                ),
                gettext_noop(
                    "Wurzel ziehen ist die Umkehrung des Quadrierens. Die Wurzel aus einer "
                    "Quadratzahl ist die Zahl, die mit sich selbst malgenommen sie ergibt."
                ),
                gettext_noop(
                    "√a ist die nichtnegative Zahl, deren Quadrat a ist. Wurzeln aus Summen darfst "
                    "du nicht einzeln ziehen; zuerst unter der Wurzel rechnen."
                ),
            ),
            gettext_noop("√36 = 6, weil 6 · 6 = 36. √0,64 = 0,8, weil 0,8 · 0,8 = 0,64."),
        ),
        Karte(
            "negative_zahlen",
            gettext_noop("Rechnen mit negativen Zahlen"),
            (
                gettext_noop(
                    "Auf dem Zahlenstrahl liegen negative Zahlen links von null. Minus mal Minus "
                    "ergibt Plus. Minus minus Minus: Zwei Minuszeichen werden zu Plus."
                ),
                gettext_noop(
                    "Negative Zahlen: Ein Minus vor einer Klammer dreht das Vorzeichen um. Plus "
                    "mal Plus und Minus mal Minus ergibt Plus; Plus mal Minus ergibt Minus. Das "
                    "gilt auch beim Teilen."
                ),
                gettext_noop(
                    "Vorzeichenregeln: gleiche Vorzeichen beim Multiplizieren und Dividieren "
                    "ergeben Plus, verschiedene Minus. a − (−b) = a + b."
                ),
            ),
            gettext_noop("−3 + 5 = 2. (−4) · (−2) = 8. 4 − (−2) = 6."),
        ),
    )
}

GENERATOR_KARTE = {
    "add_sub_100": "add_sub",
    "add_sub_1000": "add_sub",
    "einmaleins": "einmaleins",
    "umkehr": "umkehr",
    "division_ohne_rest": "division_ohne_rest",
    "geld": "geld",
    "laenge": "laenge",
    "mult_schriftlich": "mult_schriftlich",
    "div_schriftlich": "div_schriftlich",
    "bruch_kuerzen": "bruch_kuerzen",
    "bruch_erweitern": "bruch_erweitern",
    "bruch_addsub": "bruch_addsub",
    "dezimal_runden": "dezimal_runden",
    "dezimal_rechnen": "dezimal_rechnen",
    "prozent_anteil": "prozent_anteil",
    "prozent_wert": "prozent_wert",
    "groessen_umrechnen": "groessen_umrechnen",
    "punkt_vor_strich": "punkt_vor_strich",
    "klammern": "klammern",
    "gleichung_linear": "gleichung_linear",
    "term_zusammenfassen": "term_zusammenfassen",
    "term_ausmultiplizieren": "term_ausmultiplizieren",
    "prozent_rechnen": "prozent_rechnen",
    "zinsen": "zinsen",
    "dreisatz_proportional": "dreisatz_proportional",
    "dreisatz_antiproportional": "dreisatz_antiproportional",
    "potenzen": "potenzen",
    "wurzeln": "wurzeln",
    "negative_zahlen": "negative_zahlen",
}


def karte_fuer(generator):
    """Die Erklärkarte zu einer Rechenart (``None``, wenn es keine gibt)."""
    return KARTEN.get(GENERATOR_KARTE.get(generator, ""))


def karte_holen(schluessel):
    return KARTEN.get(schluessel)


def alle_karten():
    return tuple(KARTEN.values())


def karte_text(karte, sprachstufe=2, *, mit_beispiel=True):
    """Titel, Merksatz (in der Sprachstufe) und Beispiel der Karte, übersetzt."""
    stufe = max(1, min(STUFE_MAX, int(sprachstufe)))
    return KartenText(
        karte.schluessel,
        _(karte.titel),
        _(karte.stufen[stufe - 1]),
        _(karte.beispiel) if mit_beispiel else "",
    )
