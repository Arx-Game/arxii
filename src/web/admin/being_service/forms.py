"""Forms for the Being Service builder (#4333 slice 2): a being's favored resonances,
favored facets and pledge types, written together."""

from __future__ import annotations

from django import forms
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.forms import BaseInlineFormSet, inlineformset_factory

from world.magic.models import Facet
from world.worship.constants import RiteTier
from world.worship.models import BeingFacet, BeingResonance, Pledge, WorshippedBeing, WorshipRite


class BeingResonanceForm(forms.ModelForm):
    class Meta:
        model = BeingResonance
        fields = ["resonance", "tier"]


class FavoredFacetsForm(forms.Form):
    """The being's favored facets as one picker over the shared facet list; saving
    writes one ``BeingFacet`` row per facet picked and removes the rest."""

    favored_facets = forms.ModelMultipleChoiceField(
        queryset=Facet.objects.order_by("name"),
        required=False,
        widget=FilteredSelectMultiple("facets", is_stacked=False),
        help_text=(
            "Picked from the shared facet list (the flat imagery tags characters also "
            "bind). An offered item carrying one of these facets counts double, here and "
            "in ceremonies."
        ),
    )

    def save(self, being: WorshippedBeing) -> None:
        chosen = set(self.cleaned_data["favored_facets"])
        current = {row.facet: row for row in being.being_facets.select_related("facet")}
        for facet, row in current.items():
            if facet not in chosen:
                row.delete()
        for facet in chosen - set(current):
            BeingFacet.objects.create(being=being, facet=facet)


class PledgeForm(forms.ModelForm):
    """One pledge type. The closing rite picker lists only the being's own tier 1 and
    2 rites, since a tier 3 rite is a ceremony and cannot close a pledge."""

    class Meta:
        model = Pledge
        fields = ["name", "description", "favor_target", "span_weeks", "closing_rite", "is_active"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3, "cols": 60})}
        help_texts = {
            "favor_target": "Favor to earn with the being after pledging.",
            "span_weeks": "Game weeks the character has to earn it and close the pledge.",
            "closing_rite": "Lists only this being's own tier 1 and 2 rites.",
        }


class _PledgeFormSet(BaseInlineFormSet):
    """Limits every row's closing rite picker (the empty template row too) to the
    being's own tier 1 and 2 rites."""

    def add_fields(self, form, index) -> None:
        super().add_fields(form, index)
        form.fields["closing_rite"].queryset = WorshipRite.objects.filter(
            being=self.instance, kind__tier__in=[RiteTier.DEVOTIONAL, RiteTier.DEMANDING]
        ).select_related("kind")


BeingResonanceFormSet = inlineformset_factory(
    WorshippedBeing, BeingResonance, form=BeingResonanceForm, extra=0, can_delete=True
)
PledgeFormSet = inlineformset_factory(
    WorshippedBeing,
    Pledge,
    form=PledgeForm,
    formset=_PledgeFormSet,
    extra=0,
    can_delete=True,
)
