from django import template

from apps.kern import sprache

register = template.Library()


@register.filter
def uebersetzt(text):
    """``{{ rang.name|uebersetzt }}``: Start-Inhalte aus der Datenbank in der aktiven Sprache."""
    return sprache.uebersetzt(text)
