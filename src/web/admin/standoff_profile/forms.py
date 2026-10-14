"""Forms for the Standoff Profile Builder (#4354): a creature's cause, drives and faction rules."""

from __future__ import annotations

from django import forms
from django.forms import inlineformset_factory

from world.combat.models import CreatureTemplate
from world.standoffs.models import CreatureDrive, FactionRule


class StandoffProfileForm(forms.ModelForm):
    """The creature template's own standoff fields: why it would fight, and its margin."""

    class Meta:
        model = CreatureTemplate
        fields = ["cause", "cause_margin_percent"]
        help_texts = {
            "cause": (
                "Why they would start a fight on their own. Predation: they hunt the weak. "
                "Orders: they hold what they were told to hold, and fire when provoked or "
                "outmatched."
            ),
            "cause_margin_percent": (
                "How much stronger the party must look before they hold back. 10 means the "
                "party must outweigh them by a tenth."
            ),
        }


class CreatureDriveForm(forms.ModelForm):
    class Meta:
        model = CreatureDrive
        fields = ["property", "strength"]


class FactionRuleForm(forms.ModelForm):
    """One faction rule. ``rule`` is the predicate tree, typed as JSON until the predicate
    widget lands with organization and society rules (a later slice of #4121)."""

    rule = forms.JSONField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "cols": 60}),
        help_text=(
            "The test, as a predicate tree over the acting character "
            '(for example {"leaf": "has_capability", "params": {"name": "Warding"}}). '
            "Empty matches everyone."
        ),
    )

    class Meta:
        model = FactionRule
        fields = [
            "rule",
            "deed_archetype",
            "difficulty_shift_bands",
            "drive",
            "drive_shift",
            "suppresses_cause",
            "angle_text",
            "revealed_text",
        ]
        widgets = {
            "angle_text": forms.Textarea(attrs={"rows": 2, "cols": 60}),
            "revealed_text": forms.Textarea(attrs={"rows": 2, "cols": 60}),
        }

    def clean_rule(self) -> dict:
        return self.cleaned_data.get("rule") or {}


CreatureDriveFormSet = inlineformset_factory(
    CreatureTemplate,
    CreatureDrive,
    form=CreatureDriveForm,
    extra=0,
    can_delete=True,
)

FactionRuleFormSet = inlineformset_factory(
    CreatureTemplate,
    FactionRule,
    form=FactionRuleForm,
    extra=0,
    can_delete=True,
)
