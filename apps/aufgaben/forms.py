from django import forms

from apps.konten import selectors as konten_selectors

from . import wiederholung
from .models import Aufgabe, Kategorie, Status, Vorlage
from .symbole import SYMBOLE
from .wiederholung import Plan, maske_aus_tagen, tage_aus_maske


def _stil(form):
    """CSS-Klassen des Designsystems an alle Widgets hängen."""
    for feld in form.fields.values():
        w = feld.widget
        if isinstance(w, forms.CheckboxInput):
            w.attrs.setdefault("class", "kontrollkasten")
        elif isinstance(w, forms.CheckboxSelectMultiple | forms.RadioSelect | forms.HiddenInput):
            continue
        else:
            w.attrs.setdefault("class", "feld__eingabe")


class PlanFelderMixin(forms.Form):
    """Gemeinsame Formularfelder für Wiederholung/Zeitfenster/Limit (Aufgabe und Vorlage)."""

    wiederholungsart = forms.ChoiceField(
        label="Wiederholung",
        choices=wiederholung.ARTEN,
        initial=wiederholung.EINMALIG,
        widget=forms.RadioSelect,
    )
    wochentage = forms.MultipleChoiceField(
        label="An diesen Wochentagen",
        required=False,
        choices=[(str(n), kurz) for n, kurz, _ in wiederholung.WOCHENTAGE],
        widget=forms.CheckboxSelectMultiple,
    )
    intervall_tage = forms.IntegerField(
        label="Alle ... Tage", required=False, min_value=1, max_value=365
    )
    fenster_von = forms.TimeField(
        label="Frühestens ab (Uhrzeit)",
        required=False,
        widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
    )
    fenster_bis = forms.TimeField(
        label="Erledigt bis (Uhrzeit)",
        required=False,
        help_text="Gesetzt = zeitgebunden: nach dieser Frist verfällt der Termin.",
        widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
    )
    fenster_tage = forms.IntegerField(
        label="Frist liegt ... Tage später",
        required=False,
        min_value=0,
        max_value=30,
        help_text="Zum Beispiel Mi 18:00 bis Do 07:00 = 1 Tag später.",
    )
    limit_anzahl = forms.IntegerField(
        label="Höchstens ... mal", required=False, min_value=1, max_value=99
    )
    limit_zeitraum = forms.ChoiceField(
        label="pro", required=False, choices=[("", "(kein Limit)"), *wiederholung.ZEITRAEUME]
    )

    def clean_wochentage(self):
        return maske_aus_tagen(self.cleaned_data.get("wochentage") or []) or None


class AufgabeForm(PlanFelderMixin, forms.ModelForm):
    start_datum = forms.DateField(
        label="Start",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    end_datum = forms.DateField(
        label="Ende (optional)",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )

    class Meta:
        model = Aufgabe
        fields = [
            "titel",
            "punkte",
            "beschreibung",
            "kategorie",
            "freigabeart",
            "zugewiesen_an",
            "vorlage",
            "sonderpunkte_deckel_prozent",
            "wiederholungsart",
            "wochentage",
            "intervall_tage",
            "start_datum",
            "end_datum",
            "fenster_von",
            "fenster_bis",
            "fenster_tage",
            "limit_anzahl",
            "limit_zeitraum",
        ]
        widgets = {"beschreibung": forms.Textarea(attrs={"rows": 3}), "vorlage": forms.HiddenInput}
        labels = {
            "punkte": "Punkte",
            "titel": "Titel",
            "beschreibung": "Beschreibung (optional)",
            "zugewiesen_an": "Nur für dieses Kind (optional)",
            "sonderpunkte_deckel_prozent": "Deckel für Sonderpunkte in % (leer = Standard)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["kategorie"].queryset = Kategorie.objects.filter(aktiv=True)
        if self.instance.pk and self.instance.kategorie_id:
            self.fields["kategorie"].queryset |= Kategorie.objects.filter(
                pk=self.instance.kategorie_id
            )
        self.fields["kategorie"].empty_label = "(keine)"
        self.fields["zugewiesen_an"].queryset = konten_selectors.aktive_kinder()
        self.fields["zugewiesen_an"].empty_label = "Alle Kinder"
        self.fields["vorlage"].required = False
        if self.instance.pk and not self.is_bound:
            self.initial["wochentage"] = [str(t) for t in tage_aus_maske(self.instance.wochentage)]
        _stil(self)

    def clean_titel(self):
        return self.cleaned_data["titel"].strip()


class VorlageForm(PlanFelderMixin, forms.ModelForm):
    class Meta:
        model = Vorlage
        fields = ["titel", "punkte", "beschreibung", "kategorie", "freigabeart", "aktiv"]
        widgets = {"beschreibung": forms.Textarea(attrs={"rows": 3})}
        labels = {"beschreibung": "Beschreibung (optional)"}

    # Wiederholung ist optional, solange nichts angegeben ist -> einmalig ohne JSON.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["wiederholungsart"].required = False
        self.fields["kategorie"].queryset = Kategorie.objects.filter(aktiv=True)
        if self.instance.pk and self.instance.kategorie_id:
            self.fields["kategorie"].queryset |= Kategorie.objects.filter(
                pk=self.instance.kategorie_id
            )
        self.fields["kategorie"].empty_label = "(keine)"
        if self.instance.pk and not self.is_bound:
            plan = self.instance.plan
            self.initial.update(
                wiederholungsart=plan.art,
                wochentage=[str(t) for t in plan.wochentage_liste],
                intervall_tage=plan.intervall_tage,
                fenster_von=plan.fenster_von,
                fenster_bis=plan.fenster_bis,
                fenster_tage=plan.fenster_tage,
                limit_anzahl=plan.limit_anzahl,
                limit_zeitraum=plan.limit_zeitraum,
            )
        _stil(self)

    def clean(self):
        daten = super().clean()
        plan = Plan(
            art=daten.get("wiederholungsart") or wiederholung.EINMALIG,
            wochentage=daten.get("wochentage"),
            intervall_tage=daten.get("intervall_tage"),
            fenster_von=daten.get("fenster_von"),
            fenster_bis=daten.get("fenster_bis"),
            fenster_tage=daten.get("fenster_tage"),
            limit_anzahl=daten.get("limit_anzahl"),
            limit_zeitraum=daten.get("limit_zeitraum") or "",
        )
        for feld, meldung in wiederholung.pruefen(plan).items():
            self.add_error(feld, meldung)
        if not self.errors:
            standard = Plan()
            self.plan = plan
            self.wiederholung_json = None if plan == standard else plan.als_json()
        return daten

    def _post_clean(self):
        if not self.errors:
            self.instance.wiederholung = self.wiederholung_json
        super()._post_clean()


class KategorieForm(forms.ModelForm):
    symbol = forms.ChoiceField(label="Symbol", choices=SYMBOLE)

    class Meta:
        model = Kategorie
        fields = ["name", "symbol", "farbe", "reihenfolge", "aktiv"]
        labels = {"farbe": "Farbe (#rrggbb, optional)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _stil(self)


class AufgabenFilterForm(forms.Form):
    kategorie = forms.ModelChoiceField(
        Kategorie.objects.all(), required=False, empty_label="Alle Kategorien"
    )
    status = forms.ChoiceField(
        required=False, choices=[("", "Alle (ohne beendete)"), *Status.choices]
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _stil(self)
