from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Familienbelohnung

SYMBOLE = [
    ("geschenk", _("Geschenk")),
    ("kueche", _("Küche")),
    ("controller", _("Spiele")),
    ("tv", _("Film")),
    ("stern", _("Stern")),
    ("garten", _("Garten")),
    ("pokal", _("Pokal")),
    ("sonne", _("Sonne")),
    ("mond", _("Mond")),
]


def _eingabe(feld):
    feld.widget.attrs.setdefault("class", "feld__eingabe")
    return feld


class BelohnungForm(forms.ModelForm):
    symbol = forms.ChoiceField(choices=SYMBOLE, label=_("Symbol"))

    class Meta:
        model = Familienbelohnung
        fields = ["titel", "symbol", "ist_grossziel"]
        labels = {"titel": _("Name"), "ist_grossziel": _("Großes Ziel (Ausflug o. Ä.)")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("titel", "symbol"):
            _eingabe(self.fields[name])


class WocheForm(forms.Form):
    ziel_punkte = forms.IntegerField(label=_("Ziel in Punkten"), min_value=1, max_value=100000)
    belohnung = forms.ModelChoiceField(
        label=_("Belohnung"),
        queryset=Familienbelohnung.objects.none(),
        required=False,
        empty_label=_("(keine Änderung)"),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _eingabe(self.fields["ziel_punkte"])
        _eingabe(self.fields["belohnung"])
        self.fields["belohnung"].queryset = Familienbelohnung.objects.filter(
            aktiv=True, ist_grossziel=False
        )
