"""Forms for the Being Service builder (#4333 slice 2): a being's favored resonances,
favored facets (with their worn rates, #4520) and pledge types, written together."""

from __future__ import annotations

from django import forms
from django.forms import (
    BaseInlineFormSet,
    BaseModelFormSet,
    inlineformset_factory,
    modelformset_factory,
)

from world.worship.constants import RiteTier
from world.worship.models import (
    BeingFacet,
    BeingResonance,
    Pledge,
    RequestedItem,
    WorshippedBeing,
    WorshipRite,
)


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


_PLEDGE_PREFIX = "pledge"
_RITE_PREFIX = "rite"


def target_choices(being: WorshippedBeing) -> list[tuple[str, str]]:
    """What a request can belong to: one of the being's saved pledges or rites, as
    ``"pledge:<pk>"`` / ``"rite:<pk>"`` (a new pledge is saved before it can ask for anything).
    Only tier 1 and 2 rites can ask: a tier 3 rite is a ceremony, whose offerings feed the pool
    and the officiant's devotion instead of easing a roll."""
    choices = [
        (f"{_PLEDGE_PREFIX}:{pledge.pk}", f"Pledge: {pledge.name}")
        for pledge in Pledge.objects.filter(being=being).order_by("name")
    ]
    choices.extend(
        (f"{_RITE_PREFIX}:{rite.pk}", f"Rite: {rite.name}")
        for rite in WorshipRite.objects.filter(
            being=being, kind__tier__in=[RiteTier.DEVOTIONAL, RiteTier.DEMANDING]
        ).order_by("name")
    )
    return choices


class RequestedItemForm(forms.ModelForm):
    """One item a pledge or rite asks for (#4530): exactly one of a template or a facet, a
    quantity, the points each gives and a hint line. ``target`` picks the pledge or rite
    the row belongs to. A template above the value limit is refused (requests are cheap)."""

    target = forms.ChoiceField(label="For")

    class Meta:
        model = RequestedItem
        fields = ["item_template", "facet", "quantity", "points", "hint"]
        widgets = {
            "quantity": forms.NumberInput(attrs={"min": 1, "style": "width: 5em"}),
            "points": forms.NumberInput(attrs={"min": 1, "style": "width: 5em"}),
            "hint": forms.TextInput(attrs={"size": 40}),
        }

    def __init__(self, *args, target_choices_for: list[tuple[str, str]], **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["target"].choices = target_choices_for
        instance = self.instance
        if instance.pk is not None:
            self.initial["target"] = (
                f"{_PLEDGE_PREFIX}:{instance.pledge_id}"
                if instance.pledge_id is not None
                else f"{_RITE_PREFIX}:{instance.rite_id}"
            )

    def clean(self) -> dict:
        """Point the row at the chosen pledge or rite before the model validates it."""
        cleaned = super().clean()
        kind, _, pk = (cleaned.get("target") or "").partition(":")
        self.instance.pledge = (
            Pledge.objects.filter(pk=pk).first() if kind == _PLEDGE_PREFIX else None
        )
        self.instance.rite = (
            WorshipRite.objects.filter(pk=pk).first() if kind == _RITE_PREFIX else None
        )
        return cleaned


class _RequestedItemFormSet(BaseModelFormSet):
    def __init__(self, *args, being: WorshippedBeing, **kwargs) -> None:
        self._target_choices = target_choices(being)
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index: int | None) -> dict:
        kwargs = super().get_form_kwargs(index)
        kwargs["target_choices_for"] = self._target_choices
        return kwargs


RequestedItemFormSet = modelformset_factory(
    RequestedItem,
    form=RequestedItemForm,
    formset=_RequestedItemFormSet,
    extra=0,
    can_delete=True,
)
