from decimal import Decimal, InvalidOperation

from django import forms

from .models import Belohnung, Belohnungskategorie
from .symbole import SYMBOLE


def _stil(form):
    for feld in form.fields.values():
        w = feld.widget
        if isinstance(w, forms.CheckboxInput):
            w.attrs.setdefault("class", "kontrollkasten")
        elif not isinstance(w, forms.HiddenInput):
            w.attrs.setdefault("class", "feld__eingabe")


class EuroFeld(forms.Field):
    """Eurobetrag (``1``, ``2,50``) -> Cent."""

    widget = forms.TextInput(attrs={"inputmode": "decimal"})

    def __init__(self, *, max_euro=1000, **kwargs):
        self.max_euro = max_euro
        super().__init__(**kwargs)

    def prepare_value(self, value):
        if isinstance(value, int):
            return f"{value // 100},{value % 100:02d}"
        return value

    def to_python(self, value):
        if value in (None, ""):
            return None
        try:
            betrag = Decimal(str(value).replace("€", "").replace(",", ".").strip())
        except InvalidOperation:
            raise forms.ValidationError("Bitte einen Betrag wie 2,50 eingeben.") from None
        cent = betrag * 100
        if cent != cent.to_integral_value() or betrag < 0 or betrag > self.max_euro:
            raise forms.ValidationError(
                f"Betrag zwischen 0 und {self.max_euro} € in Cent-Schritten."
            )
        return int(cent)


class BelohnungForm(forms.ModelForm):
    betrag = EuroFeld(required=False, label="Betrag in €", help_text="Nur bei Taschengeld.")
    symbol = forms.ChoiceField(
        required=False, choices=[("", "wie Kategorie"), *SYMBOLE], label="Symbol"
    )

    class Meta:
        model = Belohnung
        fields = ["titel", "kategorie", "preis_punkte", "symbol", "reihenfolge", "aktiv"]
        labels = {"preis_punkte": "Preis in Punkten", "reihenfolge": "Reihenfolge"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["preis_punkte"].min_value = 1
        self.fields["preis_punkte"].widget.attrs["min"] = 1
        if self.instance.pk:
            self.initial["betrag"] = self.instance.geldwert_cent
        self.order_fields(
            ["titel", "kategorie", "preis_punkte", "betrag", "symbol", "reihenfolge", "aktiv"]
        )
        _stil(self)

    def clean_preis_punkte(self):
        preis = self.cleaned_data["preis_punkte"]
        if preis < 1:
            raise forms.ValidationError("Der Preis muss mindestens 1 Punkt sein.")
        return preis

    def _post_clean(self):
        # geldwert_cent vor der Modellvalidierung setzen (Pflicht nur bei Taschengeld)
        kategorie = self.cleaned_data.get("kategorie")
        cent = self.cleaned_data.get("betrag")
        self.instance.geldwert_cent = cent if kategorie and kategorie.ist_taschengeld else None
        if kategorie and not kategorie.ist_taschengeld and cent:
            self.add_error("betrag", "Nur Taschengeld hat einen Betrag.")
        if kategorie and kategorie.ist_taschengeld and not cent:
            self.add_error("betrag", "Taschengeld braucht einen Betrag.")
        if "betrag" in self.errors:
            return  # Modell-clean würde denselben Fehler auf ein Feld melden, das es nicht gibt
        super()._post_clean()


class KategorieForm(forms.ModelForm):
    symbol = forms.ChoiceField(choices=SYMBOLE, label="Symbol")

    class Meta:
        model = Belohnungskategorie
        fields = ["name", "symbol", "reihenfolge"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _stil(self)


class LimitForm(forms.Form):
    """Standard-Monatslimit in Euro."""

    betrag = EuroFeld(label="Standard-Limit pro Monat und Kind (€)", max_euro=1000, required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _stil(self)


class KindLimitForm(forms.Form):
    """Eigenes Limit eines Kindes; leer = Standard."""

    betrag = EuroFeld(label="Eigenes Limit (€)", max_euro=1000, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _stil(self)
