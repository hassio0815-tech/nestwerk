"""Brüche wie in der Schule und der Rechenweg der echten Aufgabe."""

from apps.lernen.mathe import registry
from apps.lernen.mathe.hilfe import rechenweg
from apps.lernen.templatetags.lernen_text import schulrechnung


def test_bruch_wird_gestapelt_mit_vorlesetext():
    html = schulrechnung("Kürze: 20/24")
    assert 'class="bruch"' in html
    assert 'aria-label="20/24"' in html
    assert ">20</span>" in html and ">24</span>" in html


def test_gemischte_zahl_und_mehrere_brueche():
    assert schulrechnung("1 3/4 + 2/4").count('class="bruch"') == 2


def test_kein_html_aus_dem_text():
    html = schulrechnung("<script>alert(1)</script> 1/2")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_keine_brueche_in_datum_oder_ketten():
    assert 'class="bruch"' not in schulrechnung("1/2/3")


def test_rechenweg_zeigt_zwischenergebnisse_der_echten_aufgabe():
    aufgabe = registry.erzeugen("bruch_kuerzen", 3, 5)
    zeilen = rechenweg(aufgabe)
    assert zeilen
    assert all("___" not in zeile for zeile in zeilen)


def test_rechenweg_fuer_jede_rechenart_ohne_fehler():
    for schluessel in registry.schluessel_alle():
        aufgabe = registry.erzeugen(schluessel, 3, 7)
        assert isinstance(rechenweg(aufgabe), list), schluessel
