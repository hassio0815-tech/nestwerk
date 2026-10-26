# Nestwerk Farb- und Designkonzept (Kurzfassung)

Quelle der Wahrheit: `static/css/tokens.css`.

## Ein Designsystem

Alle Layouts (`huelle`, `eltern`, `einrichtung`, `kind`, `tablet`) teilen Tokens, Schriften und Komponenten: Teal + Aubergine, Fraunces + Inter, runde Karten, weiche Schatten, keine Block-Rahmen, keine Pixel-Schrift.

| Bereich | Standard | Unterschied |
|---|---|---|
| Hülle, Eltern, Einrichtung | hell (oder System) | `--radius` 16px |
| Kinder, Flur-Tablet | **dunkel**, hell per `data-modus="hell"` | `--radius` 18px, `--radius-gross` 28px, etwas größere Schrift |

**Das Spiel ist Inhalt, nicht Look.** Spielerisch sind Avatar (Block-Figur bleibt kantig), Seltenheit, Ränge, Serien und die Animationen in `static/css/spiel.css` / `static/js/spiel.js`:

- Seltenheit: leuchtender Rand in `--selten-*`, God Mode = Regenbogen-Ring.
- Aufgabe geschafft: Haken-Pop, Leuchten, Punkte fliegen in den Zähler; Guthaben zählt hoch.
- Fortschritt: Balken füllt sich weich, kurzes Glühen.
- Rang-Aufstieg: Vollbild mit Konfetti in Rangfarbe, Avatar springt.
- Mod fertig: Karte dreht sich um (Loot-Enthüllung) mit Seltenheits-Glühen.
- Serie: Flamme wächst mit der Wochenserie (Stufe 0 bis 4).
- Berührung: federndes Drücken auf Knöpfen, Kacheln, PIN-Tasten.
- Alles hinter `prefers-reduced-motion: no-preference`; sonst ruhiger Zustand.

## Markenfarben

| Rolle | Token | Hell | Dunkel |
|---|---|---|---|
| Primär (Buttons, Links, Fokus) | `--akzent` | `--teal-700` #0E7C74 | `--teal-400` #2DD4B4 |
| Verlauf (Logo, Splash, Hero) | `--marke-verlauf` | #2DD4B4 → #0E7C74 | gleich |
| Sekundär / Schrift | `--text` | `--aubergine-700` #2E2152 | #F3F1F8 |
| Hintergrund | `--hintergrund` | #F7F7F4 | #15111F |
| Fläche / Karte | `--flaeche` | #FFFFFF | #1F1930 |
| Erfolg / Warnung / Gefahr / Info | `--erfolg` … `--info` | dunkle Töne | helle Töne |
| Rosé (Ablehnen = `.knopf--sanft`; `--gefahr` voll nur für Löschen) | `--rose-100/300/500/700` | #FCE7EA / #A8344F, `--gefahr` #B23A55 | transparentes Rosé / #F4A6B4 |

Volle Skalen: `--teal-50…900`, `--aubergine-50…900`.
Kontrast: Weiß auf `--teal-700` ≈ 5:1 (WCAG AA).

## Regeln

- **Persönlicher Akzent** (`--nutzer-akzent`) nur klein: Avatar-Ring, Namens-Chip, eigene Kacheln. Nie für Buttons oder Flächen.
- **Hell/Dunkel**: folgt dem System; `data-modus="hell|dunkel"` überschreibt.
- **Schrift**: Überschriften `--schrift-titel` (Fraunces), Text `--schrift-text` (Inter). Keine Pixel-Schrift.
- **Formen**: `--radius` 16px (Kinder 18px; Karten, Felder), `--radius-gross` 24px (Kinder 28px) (Hero, Launcher-Kacheln).
- **Motiv**: gekippte, abgerundete Kacheln mit Teal-Verlauf + Aubergine-Schatten (wie Logo).

- **Eltern-Bereich ohne Spiel-Optik**: XP, Ränge, Serien, Abzeichen dort als ruhige Zahlen und neutrale Pillen (keine Seltenheitsfarben, kein Glühen). Nur die Avatar-Bilder der Kinder bleiben. Spiel-Optik gilt nur im Kinderbereich (Dungeon: Avatar, Mods, Shop, Ränge, Ruhmeshalle).
