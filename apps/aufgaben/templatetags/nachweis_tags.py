from django import template

from apps.aufgaben import nachweise

register = template.Library()


@register.filter
def nachweis_fotos(meldung):
    """Dateinamen der Nachweis-Fotos einer (offenen) Meldung; leer ohne Meldung."""
    return nachweise.dateinamen(meldung.pk) if meldung is not None else []
