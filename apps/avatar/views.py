"""Auslieferung der SVG-Bilder, Erstwahl für Kinder und die Entwickler-Galerie (nur DEBUG)."""

from django.conf import settings
from django.http import Http404, HttpResponse, HttpResponseNotModified
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.konten.zugriff import nur_eltern, nur_kind, passiv

from . import selectors, services
from .generator import bibliothek

SVG_CSP = "default-src 'none'; style-src 'none'; sandbox"


@passiv
@require_GET
def svg(request, hash):
    """``GET /avatar/<hash>.svg``: unveränderliches Bild (Hash steckt in der URL)."""
    etag = f'"{hash}"'
    if request.headers.get("If-None-Match") == etag:
        antwort = HttpResponseNotModified()
    else:
        inhalt = services.svg_nach_hash(hash)
        if inhalt is None:
            raise Http404("Unbekanntes Bild")
        antwort = HttpResponse(inhalt, content_type="image/svg+xml")
    antwort["ETag"] = etag
    antwort["Cache-Control"] = "public, max-age=31536000, immutable"
    antwort["Content-Security-Policy"] = SVG_CSP
    return antwort


def _auswahl(daten):
    """Auswahl aus Formular/Abfrage, ungültige Werte werden durch Standardwerte ersetzt."""
    optionen = selectors.figur_optionen()
    standard = bibliothek.STANDARD_FIGUR
    figur = {}
    for schluessel in ("haut", "haar", "frisur"):
        gueltig = {eintrag[0] for eintrag in optionen[schluessel]}
        wert = daten.get(schluessel, "")
        figur[schluessel] = wert if wert in gueltig else standard[schluessel]
    return figur


def _vorschau_kontext(request, quelle):
    figur = _auswahl(quelle)
    themen = selectors.waehlbare_themen()
    gewaehlt = quelle.get("thema", "")
    if gewaehlt not in {t.schluessel for t in themen}:
        gewaehlt = ""
    karten = [
        {
            "thema": t,
            "svg": services.vorschau_svg(t.schluessel, figur),
            "gewaehlt": t.schluessel == gewaehlt,
        }
        for t in themen
    ]
    haupt = services.vorschau_svg(gewaehlt or bibliothek.ELTERN_THEMA, figur)
    return {"figur": figur, "karten": karten, "gewaehlt": gewaehlt, "haupt": haupt}


@nur_kind
@require_http_methods(["GET", "POST"])
def kind_wahl(request):
    """Erstwahl: Figur (Hautton, Haare, Frisur) und Thema. Themenwechsel: AP26."""
    if selectors.hat_avatar(request.user):
        return redirect("oberflaeche:kind_heim")
    fehler = ""
    if request.method == "POST":
        try:
            services.avatar_waehlen(
                request.user, request.POST.get("thema", ""), _auswahl(request.POST)
            )
        except services.AvatarFehler as exc:
            fehler = str(exc)
        else:
            return redirect("oberflaeche:kind_heim")
    quelle = request.POST if request.method == "POST" else request.GET
    kontext = {"optionen": selectors.figur_optionen(), "fehler": fehler}
    kontext.update(_vorschau_kontext(request, quelle))
    if request.headers.get("HX-Request") == "true":
        return render(request, "avatar/_vorschau.html", kontext)
    return render(request, "avatar/wahl.html", kontext)


@require_GET
def galerie(request):
    """Grundfiguren aller Themen (dunkel und hell); mit ``?thema=`` die 36 Mods dieses Themas als
    Raster. Nur im Entwicklungsmodus."""
    if not settings.DEBUG:
        raise Http404
    figuren = [
        {
            "haut": f"haut{1 + i % 6}",
            "haar": f"haar{1 + (i * 3) % 8}",
            "frisur": ("kurz", "struppig", "lang")[i % 3],
        }
        for i in range(len(bibliothek.themen()))
    ]
    themen = [
        {"thema": t, "svg": services.vorschau_svg(t["schluessel"], figuren[i])}
        for i, t in enumerate(bibliothek.themen().values())
    ]
    mod_themen = bibliothek.kind_themen()
    gewaehlt = request.GET.get("thema", "")
    gewaehlt_name = ""
    mods = []
    if gewaehlt:
        if gewaehlt not in {t["schluessel"] for t in mod_themen}:
            raise Http404
        gewaehlt_name = bibliothek.thema(gewaehlt)["name"]
        from .models import ModDefinition

        mods = [
            {
                "mod": m,
                "svg": services.vorschau_svg(
                    m.thema.schluessel, mods={m.slot.schluessel: m.render_mod()}
                ),
            }
            for m in ModDefinition.objects.select_related("thema", "slot")
            .filter(thema__schluessel=gewaehlt)
            .order_by("seltenheit", "slot__ebene")
        ]
    kontext = {
        "themen": themen,
        "mod_themen": mod_themen,
        "gewaehlt": gewaehlt,
        "gewaehlt_name": gewaehlt_name,
        "mods": mods,
    }
    return render(request, "avatar/galerie.html", kontext)


@nur_kind
@require_POST
def name_setzen(request):
    """Kind benennt oder benennt um (HTMX: nur der Namensblock kommt zurück)."""
    fehler = ""
    try:
        services.avatar_name_setzen(request.user, request.POST.get("name", ""))
    except services.AvatarFehler as exc:
        fehler = str(exc)
    if request.headers.get("HX-Request") == "true":
        kontext = {"name": services.avatar_name(request.user), "fehler": fehler}
        return render(request, "avatar/_name.html", kontext, status=422 if fehler else 200)
    return redirect("oberflaeche:dungeon")


@nur_eltern
@require_POST
def name_zuruecksetzen(request, kind_id):
    from apps.konten.models import Benutzer, Rolle

    kind = Benutzer.objects.filter(pk=kind_id, rolle=Rolle.KIND).first()
    if kind is None:
        raise Http404
    services.avatar_name_zuruecksetzen(kind, von=request.user)
    return redirect("oberflaeche:eltern_dungeon")
