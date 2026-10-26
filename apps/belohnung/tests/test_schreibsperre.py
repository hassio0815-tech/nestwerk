"""Review AP19, B-10: belohnung nutzt die Schreibsperre von punkte statt einer Kopie."""

from apps.belohnung import services as belohnung
from apps.punkte import services as punkte


def test_belohnung_nutzt_dieselbe_sperre_wie_punkte():
    assert not hasattr(belohnung, "_schreibsperre")
    assert belohnung.punkte_services.schreibsperre is punkte.schreibsperre
