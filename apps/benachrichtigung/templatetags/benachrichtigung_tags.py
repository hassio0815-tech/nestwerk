from django import template

from apps.benachrichtigung import selectors

register = template.Library()


@register.inclusion_tag("benachrichtigung/_reiter_zaehler.html", takes_context=True)
def reiter_zaehler(context):
    """Kleine Zahl am Reiter "Benachrichtigungen": nur offene Einträge, nur wenn > 0."""
    request = context.get("request")
    benutzer = getattr(request, "user", None)
    offen = 0
    if benutzer is not None and benutzer.is_authenticated and benutzer.rolle == "eltern":
        offen = selectors.offene_anzahl(benutzer)
    return {"offen": offen}
