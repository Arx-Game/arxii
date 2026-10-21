"""Forms for the Being Service builder (#4333 slice 2): a being's favored resonances,
favored facets (with their worn rates, #4520) and pledge types, written together."""

from __future__ import annotations

from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from world.worship.constants import RiteTier
from world.worship.models import BeingFacet, BeingResonance, Pledge, WorshippedBeing, WorshipRite


class BeingResonanceForm(forms.ModelForm):
    class Meta:
        model = BeingResonance
        fields = ["resonance", "tier"]


class BeingFacetForm(forms.ModelForm):
    """One favored facet with its worn rates (#4520): the difficulty points a worn piece
    carrying it eases an invocation by, and the percent it adds to the earning rate, each
    per meaning point of the piece."""

    class Meta:
        model = BeingFacet
        fields = ["facet", "invocation_ease_points", "earning_bonus_percent"]
        widgets = {
            "invocation_ease_points": forms.NumberInput(attrs={"min": 0, "style": "width: 6em"}),
            "earning_bonus_percent": forms.NumberInput(attrs={"min": 0, "style": "width: 6em"}),
        }


class PledgeForm(forms.ModelForm):
    """One pledge type. The closing rite picker lists only the being's own tier 1 and
    2 rites, since a tier 3 rite is a ceremony and cannot close a pledge."""

    class Meta:
        model = Pledge
        fields = ["name", "description", "favor_target", "span_weeks", "closing_rite", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "vTextField", "size": 60}),
            "description": forms.Textarea(attrs={"rows": 3, "cols": 60}),
        }
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


BeingFacetFormSet = inlineformset_factory(
    WorshippedBeing, BeingFacet, form=BeingFacetForm, extra=0, can_delete=True
)
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
