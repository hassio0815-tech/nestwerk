from django import forms
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.kern import zeit
from apps.konten import selectors as konten

FAMILIE = "familie"


class PauseForm(forms.Form):
    ziel = forms.ChoiceField(label=gettext_lazy("Für wen?"))
    von = forms.DateField(
        label=gettext_lazy("Ab"), widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
    )
    bis = forms.DateField(
        label=gettext_lazy("Bis (einschließlich)"),
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        help_text=gettext_lazy("Leer lassen = offen, bis ihr die Pause ausschaltet."),
    )
    grund = forms.CharField(label=gettext_lazy("Grund (optional)"), max_length=120, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.kinder = list(konten.aktive_kinder())
        self.fields["ziel"].choices = [(FAMILIE, _("Ganze Familie"))] + [
            (str(k.pk), k.anzeigename) for k in self.kinder
        ]
        self.fields["von"].initial = zeit.heute()

    def clean(self):
        daten = super().clean()
        von, bis = daten.get("von"), daten.get("bis")
        if von and bis and bis < von:
            self.add_error("bis", _("Das Ende liegt vor dem Beginn."))
        return daten

    def ziel_kind(self):
        """Gewähltes Kind oder ``None`` (Familie)."""
        ziel = self.cleaned_data["ziel"]
        return next((k for k in self.kinder if str(k.pk) == ziel), None)
