# Lizenz: offene Entscheidung

Status: **nicht entschieden.** Im Repository liegt bewusst keine `LICENSE`-Datei. Die Entscheidung trifft der Projektinhaber.

## Optionen

- **MIT:** Sehr frei. Jeder darf den Code auch in geschlossenen Produkten nutzen, ändern und verkaufen, ohne etwas zurückzugeben.
- **AGPL-3.0:** Copyleft. Wer FamKo geändert als Dienst im Netz betreibt, muss die Änderungen ebenfalls veröffentlichen. Das passt zu einer Selbsthosting-App, die andere Familien betreiben.
- **GPL-3.0:** Copyleft ohne Netz-Klausel. Änderungen müssen nur weitergegeben werden, wenn Software verteilt wird. Ein gehosteter Dienst fällt nicht darunter.

## Empfehlung

**AGPL-3.0.** Begründung:

- FamKo wird von Familien selbst gehostet. Eine AGPL schützt davor, dass jemand eine geänderte Fassung als geschlossenen Online-Dienst anbietet, ohne Verbesserungen zurückzugeben.
- Die Abhängigkeiten sind überwiegend permissiv (u. a. BSD, MIT, Apache-2.0). Die Schriften Inter und Press Start 2P stehen unter der SIL OFL. pywebpush steht unter MPL-2.0, und MPL-2.0 nennt die AGPL als Sekundärlizenz.
- Gegen MIT spricht nichts Fachliches. Wer FamKo nur für sich nutzt, merkt keinen Unterschied.

Vor der Veröffentlichung: Abhängigkeiten mit einem Lizenz-Werkzeug (z. B. `pip-licenses`) prüfen. Die Lizenzhinweise der Schriften in `static/fonts/` beibehalten.
