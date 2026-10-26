"""Mod-Shop, Werkstatt, Slots und Themenwechsel (Kind) sowie Bauaufträge und Mod-Standards
(Eltern), AP26."""

from decimal import Decimal, InvalidOperation

from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.konten.zugriff import nur_eltern, nur_kind
from apps.punkte import selectors as punkte_selectors
from apps.spielregeln import selectors as raenge
from apps.spielregeln.services import RangFehler

from . import selectors, services
from .models import Slot

# Feste Erfolgsmeldungen (kein frei wählbarer Text in der URL)
MELDUNGEN = {
    "gekauft": "Gekauft! Dein Mod ist jetzt im Bau.",
    "fertig": "Dein Mod ist fertig und angelegt.",
    "angelegt": "Angelegt!",
    "abgelegt": "Slot ist jetzt leer.",
    "thema": "Neues Thema! Deine Slots sind leer – auf zu neuen Mods.",
    "sofort": "Bau fertiggestellt.",
    "standard": "Gespeichert.",
}


def _meldung(request):
    return MELDUNGEN.get(request.GET.get("ok", ""), "")


def _shop_kontext(request, fehler=""):
    kind = request.user
    avatar = selectors.avatar_von(kind)
    ort, taetigkeit = selectors.inszenierung(avatar.thema)
    _, svg = services.svg_fuer(kind)
    return {
        "avatar": avatar,
        "svg": svg,
        "verfuegbar": punkte_selectors.verfuegbar(kind),
        "stufe": selectors.ausbaustufe(kind),
        "bau": selectors.bauauftraege(kind),
        "gruppen": _mit_vorschau(kind, selectors.shop(kind)),
        "fertige": _mit_rang(selectors.eigene_fertige(kind)),
        "angelegt": set((avatar.angelegt or {}).values()),
        "ort": ort,
        "taetigkeit": taetigkeit,
        "fehler": fehler,
        "meldung": "" if fehler else _meldung(request),
    }


def _mit_vorschau(kind, gruppen):
    """Je Karte der eigene Avatar mit diesem Mod (Vorschau, ohne Speicherung)."""
    basis = services.vorschau_basis(kind)
    for g in gruppen:
        for k in g.karten:
            k.svg = services.vorschau_mit_mod(kind, k.mod, basis)
    return gruppen


def _mit_rang(besitze):
    """Seltenheitsfarbe und Rangname je Mod (Chip)."""
    raenge_map = {r.stufe: r for r in raenge.raenge()}
    for b in besitze:
        rang = raenge_map.get(b.mod.seltenheit)
        b.selten = rang.selten if rang else "common"
        b.rang_name = rang.name if rang else str(b.mod.seltenheit)
    return besitze


@nur_kind
@require_GET
def shop(request):
    if not selectors.hat_avatar(request.user):
        return redirect("avatar:kind_wahl")
    kontext = _shop_kontext(request)
    slot = Slot.objects.filter(schluessel=request.GET.get("slot", "")).first()
    if slot is not None:  # Filter aus dem Charakter-Bildschirm: nur Mods dieses Slots
        gruppen = []
        for g in kontext["gruppen"]:
            g.karten = [k for k in g.karten if k.mod.slot_id == slot.pk]
            if g.karten:
                gruppen.append(g)
        kontext.update(gruppen=gruppen, slot_filter=slot)
    return render(request, "avatar/shop.html", kontext)


def _mod_oder_404(request, schluessel):
    avatar = selectors.avatar_von(request.user)
    mod = selectors.mod(schluessel)
    if avatar is None or mod is None or mod.thema_id != avatar.thema_id or not mod.aktiv:
        raise Http404("Unbekannter Mod")
    return avatar, mod


def _mod_kontext(request, mod, fehler=""):
    kind = request.user
    karte = next((k for g in selectors.shop(kind) for k in g.karten if k.mod.pk == mod.pk), None)
    if karte is None:
        raise Http404("Unbekannter Mod")
    avatar = selectors.avatar_von(kind)
    ort, taetigkeit = selectors.inszenierung(avatar.thema)
    return {
        "karte": karte,
        "mod": mod,
        "svg": services.vorschau_mit_mod(kind, mod),
        "verfuegbar": punkte_selectors.verfuegbar(kind),
        "ort": ort,
        "taetigkeit": taetigkeit,
        "fehler": fehler,
        "kauf_text": f"Kaufen für {karte.konditionen.preis} Punkte",
        "fehlt_text": f"Dir fehlen noch {karte.fehlt} Punkte",
        "gesperrt_text": f"Ab Rang {karte.konditionen.rang_name}",
    }


@nur_kind
@require_GET
def mod_detail(request, schluessel):
    _, mod = _mod_oder_404(request, schluessel)
    return render(request, "avatar/mod.html", _mod_kontext(request, mod))


@nur_kind
@require_POST
def kaufen(request, schluessel):
    _, mod = _mod_oder_404(request, schluessel)
    try:
        besitz = services.mod_kaufen(request.user, mod)
    except services.ModFehler as exc:
        return render(request, "avatar/mod.html", _mod_kontext(request, mod, str(exc)), status=409)
    return redirect(_url("avatar:shop", "fertig" if besitz.status == "fertig" else "gekauft"))


@nur_kind
@require_POST
def anlegen(request, schluessel):
    _, mod = _mod_oder_404(request, schluessel)
    try:
        services.mod_anlegen(request.user, mod)
    except services.ModFehler as exc:
        return render(request, "avatar/shop.html", _shop_kontext(request, str(exc)), status=409)
    return redirect(_url("avatar:shop", "angelegt") + "#meine-mods")


@nur_kind
@require_POST
def ablegen(request, slot):
    if not selectors.hat_avatar(request.user):
        raise Http404
    services.slot_leeren(request.user, slot)
    return redirect(_url("avatar:shop", "abgelegt") + "#meine-mods")


def _url(name, ok):
    return f"{reverse(name)}?ok={ok}"


@nur_kind
@require_http_methods(["GET", "POST"])
def thema(request):
    """Themenwechsel: Auswahl, dann Warn-Dialog mit konkreten Zahlen, dann Bestätigung."""
    kind = request.user
    avatar = selectors.avatar_von(kind)
    if avatar is None:
        return redirect("avatar:kind_wahl")
    fehler = ""
    gewaehlt = (request.POST if request.method == "POST" else request.GET).get("thema", "")
    if request.method == "POST":
        try:
            services.thema_wechseln(kind, gewaehlt, pruefwert=request.POST.get("pruefwert", ""))
        except services.ModFehler as exc:
            fehler = str(exc)
        else:
            return redirect(_url("avatar:shop", "thema"))
    warnung = None
    if gewaehlt:
        try:
            warnung = services.themenwechsel_vorschau(kind, gewaehlt)
        except services.ModFehler as exc:
            fehler = fehler or str(exc)
    karten = [
        {
            "thema": t,
            "svg": services.vorschau_svg(t.schluessel, avatar.figur),
            "aktuell": t.pk == avatar.thema_id,
            "gewaehlt": t.schluessel == gewaehlt,
        }
        for t in selectors.waehlbare_themen()
    ]
    kontext = {
        "avatar": avatar,
        "karten": karten,
        "warnung": warnung,
        "warnung_svg": services.vorschau_svg(warnung.neu.schluessel, avatar.figur)
        if warnung
        else "",
        "fehler": fehler,
    }
    return render(request, "avatar/thema.html", kontext, status=409 if fehler and warnung else 200)


# --- Eltern ---------------------------------------------------------------------------------


@nur_eltern
@require_GET
def eltern(request):
    return render(request, "avatar/eltern.html", _eltern_kontext(request))


def _eltern_kontext(request, fehler=""):
    return {
        "zeilen": selectors.eltern_uebersicht(),
        "standards": selectors.mod_standards(),
        "faktor_preis": _faktor_text(raenge.preis_faktor()),
        "faktor_bauzeit": _faktor_text(raenge.bauzeit_faktor()),
        "fehler": fehler,
        "meldung": "" if fehler else _meldung(request),
    }


def _faktor_text(wert):
    return f"{wert:.2f}".replace(".", ",")


@nur_eltern
@require_POST
def sofort(request, pk):
    try:
        services.bau_sofort_fertigstellen(pk, von=request.user)
    except services.ModFehler as exc:
        return render(request, "avatar/eltern.html", _eltern_kontext(request, str(exc)), status=409)
    return redirect(_url("avatar:eltern", "sofort"))


@nur_eltern
@require_POST
def standards(request):
    """Mod-Preis und Bauzeit je Seltenheit (Rang-Standard) sowie globale Faktoren."""
    try:
        for eintrag in selectors.mod_standards():
            rang = eintrag["rang"]
            preis = request.POST.get(f"preis_{rang.stufe}", "").strip()
            tage = request.POST.get(f"bauzeit_{rang.stufe}", "").strip()
            if not preis and not tage:
                continue
            stunden = _stunden(tage, rang)
            services.mod_standard_aendern(
                rang, von=request.user, mod_preis=preis or rang.mod_preis, bauzeit_stunden=stunden
            )
        if request.POST.get("faktor_preis") or request.POST.get("faktor_bauzeit"):
            services.mod_faktoren_setzen(
                von=request.user,
                faktor_preis=request.POST.get("faktor_preis") or raenge.preis_faktor(),
                faktor_bauzeit=request.POST.get("faktor_bauzeit") or raenge.bauzeit_faktor(),
            )
    except RangFehler as exc:
        return render(request, "avatar/eltern.html", _eltern_kontext(request, str(exc)), status=400)
    return redirect(_url("avatar:eltern", "standard") + "#standards")


def _stunden(tage, rang):
    """Bauzeit-Eingabe in Tagen (Komma erlaubt, z. B. "1,5") -> Stunden."""
    if not tage:
        return rang.bauzeit_stunden
    try:
        wert = Decimal(tage.replace(",", "."))
    except InvalidOperation:
        raise RangFehler(f"{rang.name}: Bauzeit bitte in Tagen, z. B. 3 oder 1,5.") from None
    if wert < 0:
        raise RangFehler(f"{rang.name}: Bauzeit darf nicht negativ sein.")
    return int((wert * 24).to_integral_value())
