# Sicherheitsrichtlinie

🇬🇧 [English](SECURITY.md) · 🇩🇪 **Deutsch**

Nestwerk läuft in Familiennetzen und speichert Daten über Kinder. Wir nehmen Sicherheitsmeldungen ernst.

## Unterstützte Versionen

| Version | Unterstützt |
|---|---|
| `main` (neuester Commit) | Ja |
| Ältere Commits und Forks | Nein |

Bitte aktualisiere vor der Meldung auf das aktuelle `main`.

## Schwachstelle melden

**Eröffne für Sicherheitsprobleme kein öffentliches Issue.**

Nutze die private Schwachstellenmeldung von GitHub:

1. Öffne den [Reiter „Security“](https://github.com/hassio0815-tech/nestwerk/security) des Repositorys.
2. Klicke auf **Report a vulnerability**.
3. Beschreibe das Problem, die betroffene Version oder den Commit und die Schritte zum Nachstellen.

Bitte schreibe keine echten Familiendaten, Passwörter oder Tokens in die Meldung.

## Was dich erwartet

- Wir bestätigen den Eingang innerhalb weniger Tage. Nestwerk wird in der Freizeit gepflegt, bitte hab Geduld.
- Wir bewerten die Meldung, bereiten einen Fix auf `main` vor und sagen dir Bescheid, sobald er veröffentlicht ist.
- Mit deinem Einverständnis nennen wir dich im Changelog, sobald der Fix öffentlich ist.

## Geltungsbereich

Im Geltungsbereich: die Nestwerk-Anwendung, das Docker-Setup und die Skripte in `deploy/`.

Außerhalb: Probleme im eigenen Server, Reverse Proxy oder Netzwerk sowie bereits öffentlich bekannte Schwachstellen in Abhängigkeiten von Dritten (bitte dort melden; ein Hinweis an uns ist willkommen).
