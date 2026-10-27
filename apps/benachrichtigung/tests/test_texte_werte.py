"""``texte.werte_aus``: Ereignis-Daten in der aktiven Sprache (docs/i18n.md)."""

from types import SimpleNamespace

from django.utils import translation

from apps.benachrichtigung import texte


def _ereignis(**daten):
    return SimpleNamespace(daten=daten, kind_id=None, akteur_id=None)


def test_msgid_und_parameter_werden_beim_rendern_uebersetzt():
    ereignis = _ereignis(sofort_msgid="sofort", bauzeit="sofort")
    with translation.override("en"):
        assert texte.werte_aus(ereignis)["sofort"] == "right away"
    with translation.override("de"):
        assert texte.werte_aus(ereignis)["sofort"] == "sofort"


def test_mehrzahl_nach_n():
    daten = {
        "bauzeit_msgid": "%(n)s Tag",
        "bauzeit_msgid_plural": "%(n)s Tage",
    }
    with translation.override("en"):
        eins = texte.werte_aus(_ereignis(**daten, bauzeit_parameter={"n": 1}))
        drei = texte.werte_aus(_ereignis(**daten, bauzeit_parameter={"n": 3}))
    assert eins["bauzeit"] == "1 day"
    assert drei["bauzeit"] == "3 days"


def test_hinweis_aelteres_format_mit_titel():
    ereignis = _ereignis(
        hinweis_msgid="Gleichstand zwischen %(titel)s. Bitte entscheidet.",
        hinweis_titel="Eis und Kino",
    )
    with translation.override("de"):
        assert (
            texte.werte_aus(ereignis)["hinweis"]
            == "Gleichstand zwischen Eis und Kino. Bitte entscheidet."
        )
    with translation.override("en"):
        werte = texte.werte_aus(ereignis)
    assert "Eis und Kino" in werte["hinweis"]
    assert not werte["hinweis"].startswith("Gleichstand")


def test_gespeicherter_deutscher_start_inhalt_wird_uebersetzt():
    ereignis = _ereignis(belohnung="Süßes klein", aufgabe="Selbst ausgedacht", preis=15)
    with translation.override("en"):
        werte = texte.werte_aus(ereignis)
    assert werte["belohnung"] != "Süßes klein"
    assert werte["aufgabe"] == "Selbst ausgedacht"  # von Eltern eingegeben: bleibt
    assert werte["preis"] == 15


def test_kaputte_parameter_fallen_auf_die_msgid_zurueck():
    ereignis = _ereignis(x_msgid="Hallo %(name)s", x_parameter={})
    assert texte.werte_aus(ereignis)["x"] == "Hallo %(name)s"
