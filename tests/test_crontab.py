"""deploy/crontab (supercronic): Syntax, Commands vorhanden, Sommerzeit-Sperrfenster (AP18)."""

import re
import warnings
from pathlib import Path

from django.core.management import get_commands

CRONTAB = Path(__file__).resolve().parent.parent / "deploy" / "crontab"
FELDER = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]
# Command entsteht in AP12; bis dahin darf er fehlen (Warnung statt Fehler)
ERWARTET_VON_AP12 = {"reservierungen_pruefen"}
PFLICHT_JOBS = {
    "aufgaben_erzeugen",
    "verfall_pruefen",
    "reservierungen_pruefen",
    "konten_aufraeumen",
    "benachrichtigungen_aufraeumen",
    "db_sichern",
    "backup_pruefen",
    "wochen_sicherstellen",
    "familienwoche_sicherstellen",
    "mods_fertigstellen",
    "sondertag_sicherstellen",
}


def _werte(feld, minimum, maximum):
    """Expandiert ein Cron-Feld (``*``, ``*/n``, ``a-b``, ``a-b/n``, Listen) zu einer Menge."""
    ergebnis = set()
    for teil in feld.split(","):
        m = re.fullmatch(r"(\*|\d+(?:-\d+)?)(?:/(\d+))?", teil)
        assert m, f"Ungültiges Cron-Feld: {feld!r}"
        bereich, schritt = m.group(1), int(m.group(2) or 1)
        assert schritt >= 1
        if bereich == "*":
            von, bis = minimum, maximum
        elif "-" in bereich:
            von, bis = map(int, bereich.split("-"))
        else:
            von = bis = int(bereich)
            if m.group(2):
                bis = maximum
        assert minimum <= von <= bis <= maximum, f"Wert außerhalb des Bereichs: {feld!r}"
        ergebnis.update(range(von, bis + 1, schritt))
    return ergebnis


def _eintraege():
    eintraege = []
    for nr, zeile in enumerate(CRONTAB.read_text().splitlines(), 1):
        zeile = zeile.strip()
        if not zeile or zeile.startswith("#"):
            continue
        teile = zeile.split(None, 5)
        assert len(teile) == 6, f"Zeile {nr}: 5 Zeitfelder + Befehl erwartet"
        zeit, befehl = teile[:5], teile[5]
        werte = [_werte(f, *grenzen) for f, grenzen in zip(zeit, FELDER, strict=True)]
        eintraege.append((nr, werte, befehl))
    return eintraege


def _job(befehl):
    m = re.fullmatch(r"python manage\.py ([a-z_]+)(?: .*)?", befehl)
    assert m, f"Befehl muss 'python manage.py <command>' sein: {befehl!r}"
    return m.group(1)


def test_crontab_syntax_und_pflichtjobs():
    eintraege = _eintraege()
    assert eintraege
    assert PFLICHT_JOBS <= {_job(b) for _, _, b in eintraege}


def test_aufgaben_erzeugen_takte():
    minuten = [w[0] for _, w, b in _eintraege() if _job(b) == "aufgaben_erzeugen"]
    assert {0, 15, 30, 45} in minuten
    assert {5} in minuten


def test_alle_commands_existieren():
    vorhanden = set(get_commands())
    fehlend = {_job(b) for _, _, b in _eintraege()} - vorhanden
    unerwartet = fehlend - ERWARTET_VON_AP12
    assert not unerwartet, f"Commands fehlen: {sorted(unerwartet)}"
    for name in sorted(fehlend):
        warnings.warn(f"{name} fehlt noch (erwartet von AP12)", stacklevel=1)


def test_wochen_sicherstellen_stuendlich_inkl_dienstag_0010():
    """Wochenabschluss nach 24 h Puffer: Di 00:10 muss enthalten sein (stündlicher Takt)."""
    takte = [w for _, w, b in _eintraege() if _job(b) == "wochen_sicherstellen"]
    assert any(len(w[1]) == 24 and 10 in w[0] and 2 in w[4] for w in takte)


def test_feste_tagesjobs_nicht_zwischen_2_und_3_uhr():
    """Tägliche/wöchentliche Jobs meiden die Sommerzeit-Umstellung. Die Takt-Jobs (Stunde ``*``)
    sind idempotent und holen Versäumtes nach."""
    for nr, werte, _ in _eintraege():
        if len(werte[1]) == 24:
            continue
        assert 2 not in werte[1], f"Zeile {nr}: Tagesjob in der Stunde 02:xx"


def test_deploy_skripte_shellcheck():
    import shutil
    import subprocess
    import sys

    import pytest

    exe = shutil.which("shellcheck") or str(Path(sys.executable).parent / "shellcheck")
    if not Path(exe).exists():
        pytest.skip("shellcheck nicht installiert (pip install shellcheck-py)")
    skripte = sorted(str(p) for p in (CRONTAB.parent).glob("*.sh"))
    assert len(skripte) >= 5
    ergebnis = subprocess.run(
        [exe, "-x", "-P", "SCRIPTDIR", *skripte], capture_output=True, text=True, check=False
    )
    assert ergebnis.returncode == 0, ergebnis.stdout


def test_deploy_skripte_streng_und_ausfuehrbar():
    for p in CRONTAB.parent.glob("*.sh"):
        if p.name == "lib.sh":
            continue
        assert "set -euo pipefail" in p.read_text() or p.name == "entrypoint.sh", p.name
        assert p.stat().st_mode & 0o100, f"{p.name} nicht ausführbar"
