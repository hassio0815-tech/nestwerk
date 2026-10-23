import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction

from apps.ereignisse import registry, selectors, services, worker
from apps.ereignisse.models import Ereignis, EreignisTyp, EreignisVerarbeitung, Status

from .conftest import TYP, TYP_OHNE_HANDLER


class Abbruch(Exception):
    pass


@pytest.mark.django_db
def test_rollback_erzeugt_kein_ereignis(katalog):
    with pytest.raises(Abbruch), transaction.atomic():
        services.veroeffentlichen(TYP, daten={"x": 1})
        raise Abbruch
    assert not Ereignis.objects.exists()

    with transaction.atomic():
        e = services.veroeffentlichen(TYP, daten={"x": 2})
    assert Ereignis.objects.get().pk == e.pk
    assert e.daten == {"x": 2} and e.verteilt is False
    assert selectors.aktuelle_version() == e.pk


@pytest.mark.django_db(transaction=True)
def test_ohne_transaktion_verweigert(katalog):
    with pytest.raises(services.KeineTransaktion):
        services.veroeffentlichen(TYP)
    assert not Ereignis.objects.exists()


@pytest.mark.django_db
def test_schluessel_verhindert_doppeltes_ereignis(katalog):
    erstes = services.veroeffentlichen(TYP, schluessel="erinnerung:7")
    zweites = services.veroeffentlichen(TYP, schluessel="erinnerung:7")
    assert erstes.pk == zweites.pk
    services.veroeffentlichen(TYP)
    services.veroeffentlichen(TYP)  # ohne Schlüssel beliebig oft
    assert Ereignis.objects.count() == 3


@pytest.mark.django_db
def test_ungueltige_eingaben(katalog):
    with pytest.raises(registry.UnbekannterEintrag):
        services.veroeffentlichen("gibt.es_nicht")
    with pytest.raises(ValueError):
        services.veroeffentlichen(TYP, daten=["keine", "dict"])
    with pytest.raises(ValueError):
        services.veroeffentlichen(TYP, daten={"objekt": object()})
    with pytest.raises(ValueError):
        services.veroeffentlichen(TYP, schluessel="")
    with pytest.raises(ValueError):
        services.veroeffentlichen(TYP, kind=object())


@pytest.mark.django_db
def test_synchroner_handler_in_gleicher_transaktion(katalog):
    gesehen = []

    def sync_handler(ereignis):
        gesehen.append(ereignis.pk)
        if ereignis.daten.get("kaputt"):
            raise Abbruch

    registry.handler_registrieren(TYP, sync_handler, name="test.sync", synchron=True)
    e = services.veroeffentlichen(TYP)
    assert gesehen == [e.pk]
    with pytest.raises(Abbruch), transaction.atomic():
        services.veroeffentlichen(TYP, daten={"kaputt": True})
    assert Ereignis.objects.count() == 1
    # synchrone Handler erzeugen keine Worker-Verarbeitung
    worker.verteilen()
    assert not EreignisVerarbeitung.objects.exists()


@pytest.mark.django_db
def test_typ_fehlt_in_db_wird_angelegt(katalog):
    registry.typ_deklarieren("test.spaet", modul="test", bezeichnung="Spät", zielgruppe="kind")
    services.veroeffentlichen("test.spaet")
    assert EreignisTyp.objects.get(pk="test.spaet").zielgruppe == "kind"


def test_deklaration_wird_geprueft():
    with registry.isoliert():
        with pytest.raises(ImproperlyConfigured):
            registry.typ_deklarieren("ohnepunkt", modul="x", bezeichnung="x", zielgruppe="kind")
        with pytest.raises(ImproperlyConfigured):
            registry.typ_deklarieren("a.b", modul="x", bezeichnung="x", zielgruppe="alle")
        with pytest.raises(ImproperlyConfigured):
            registry.handler_registrieren("nicht.deklariert", print)
        registry.typ_deklarieren("a.b", modul="x", bezeichnung="x", zielgruppe="kind")
        with pytest.raises(ImproperlyConfigured):
            registry.typ_deklarieren("a.b", modul="x", bezeichnung="x", zielgruppe="kind")
        registry.handler_registrieren("a.b", print, name="h")
        with pytest.raises(ImproperlyConfigured):
            registry.handler_registrieren("a.b", print, name="h")
    assert "a.b" not in registry.typ_verzeichnis


@pytest.mark.django_db
def test_sync_ist_idempotent_und_ueberschreibt_keine_bearbeitung(katalog):
    assert services.typen_synchronisieren() == {"angelegt": 0, "aktualisiert": 0}
    assert EreignisTyp.objects.filter(modul="test").count() == 2
    typ = EreignisTyp.objects.get(pk=TYP)
    assert typ.standard_kanaele == ["push", "email"] and typ.aktiv

    # Eltern bearbeiten den Typ in der DB
    EreignisTyp.objects.filter(pk=TYP).update(
        bezeichnung="Geändert", standard_kanaele=["push"], aktiv=False, modul="alt"
    )
    registry.typ_deklarieren("test.neu", modul="test", bezeichnung="Neu", zielgruppe="beide")
    assert services.typen_synchronisieren() == {"angelegt": 1, "aktualisiert": 1}
    assert services.typen_synchronisieren() == {"angelegt": 0, "aktualisiert": 0}
    typ.refresh_from_db()
    assert (typ.bezeichnung, typ.standard_kanaele, typ.aktiv) == ("Geändert", ["push"], False)
    assert typ.modul == "test"  # nur das nicht editierbare Feld wird nachgeführt
    assert EreignisTyp.objects.filter(modul="test").count() == 3


@pytest.mark.django_db
def test_verteilen_ohne_handler(katalog):
    services.veroeffentlichen(TYP_OHNE_HANDLER)
    assert worker.verteilen() == 1
    assert Ereignis.objects.get().verteilt
    assert not EreignisVerarbeitung.objects.exists()
    assert worker.verteilen() == 0
    assert selectors.systemstatus()["unverteilt"] == 0


@pytest.mark.django_db
def test_seed_der_worker_einstellungen(db):
    from apps.kern import einstellungen

    assert einstellungen.wert("ereignisse.max_versuche") == 8
    assert einstellungen.wert("ereignisse.backoff_basis_sekunden") == 30


@pytest.mark.django_db
def test_status_choices_vollstaendig():
    assert set(Status.values) == {"offen", "ok", "fehler", "aufgegeben"}


@pytest.mark.django_db
def test_kind_und_akteur_werden_gespeichert_und_geprueft(katalog):
    from apps.konten import services as konten

    mama = konten.eltern_anlegen("Mama", rolle_label="mama")
    anna = konten.kind_anlegen("Anna", "4817")
    e = services.veroeffentlichen(TYP, kind=anna, akteur=mama)
    e.refresh_from_db()
    assert e.kind_id == anna.pk and e.akteur_id == mama.pk
    with pytest.raises(ValueError):
        services.veroeffentlichen(TYP, kind=mama)  # Eltern sind kein "betroffenes Kind"
    services.veroeffentlichen(TYP, akteur=anna)  # Kinder dürfen Akteur sein
    assert Ereignis.objects.count() == 2


@pytest.mark.django_db
def test_handler_fuer_alle_typen_und_nachlauf(katalog):
    gesehen = []
    registry.alle_typen_handler_registrieren(
        lambda ereignis: gesehen.append(ereignis.typ_id), name="test.alle"
    )
    registry.nachlauf_registrieren("test.nachlauf", lambda: 3)
    services.veroeffentlichen(TYP)
    services.veroeffentlichen(TYP_OHNE_HANDLER)
    ergebnis = worker.runde()
    assert sorted(gesehen) == [TYP, TYP_OHNE_HANDLER]
    assert ergebnis["nachlauf"] == 3
    with pytest.raises(ImproperlyConfigured):
        registry.alle_typen_handler_registrieren(lambda e: None, name="test.alle")


@pytest.mark.django_db
def test_nachlauf_fehler_stoppt_die_runde_nicht(katalog):
    def kaputt():
        raise RuntimeError("boom")

    registry.nachlauf_registrieren("test.kaputt", kaputt)
    registry.nachlauf_registrieren("test.gut", lambda: 1)
    assert worker.runde()["nachlauf"] == 1
