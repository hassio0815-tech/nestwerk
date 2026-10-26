"""``{% akzent_palette as farben %}``: Namen der Kind-Akzentfarben (für die Farbwahl in der Kopfleiste)."""

from django import template

from apps.konten import akzent

register = template.Library()


@register.simple_tag
def akzent_palette():
    return list(akzent.PALETTE)
