from django import forms

from .models import Familienbelohnung

SYMBOLE = [
    ("geschenk", "Geschenk"),
    ("kueche", "Küche"),
    ("controller", "Spiele"),
    ("tv", "Film"),
    ("stern", "Stern"),
    ("garten", "Garten"),
    ("pokal", "Pokal"),
    ("sonne", "Sonne"),
    ("mond", "Mond"),
]


def _eingabe(feld):
    feld.widget.attrs.setdefault("class", "feld__eingabe")
    return feld


class BelohnungForm(forms.ModelForm):
    symbol = forms.ChoiceField(choices=SYMBOLE, label="Symbol")

    class Meta:
        model = Familienbelohnung
        fields = ["titel", "symbol", "ist_grossziel"]
        labels = {"titel": "Name", "ist_grossziel": "Großes Ziel (Ausflug o. Ä.)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("titel", "symbol"):
            _eingabe(self.fields[name])


class WocheForm(forms.Form):
    ziel_punkte = forms.IntegerField(label="Ziel in Punkten", min_value=1, max_value=100000)
    belohnung = forms.ModelChoiceField(
        label="Belohnung",
        queryset=Familienbelohnung.objects.none(),
        required=False,
        empty_label="(keine Änderung)",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _eingabe(self.fields["ziel_punkte"])
        _eingabe(self.fields["belohnung"])
        self.fields["belohnung"].queryset = Familienbelohnung.objects.filter(
            aktiv=True, ist_grossziel=False
        )
