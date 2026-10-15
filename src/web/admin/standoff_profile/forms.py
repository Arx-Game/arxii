"""Forms for the Standoff Profile Builder (#4354): a creature's cause, drives and faction rules."""

from __future__ import annotations

from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import AutocompleteSelect
from django.forms import inlineformset_factory

from web.admin.predicate_widget import PredicateRuleField
from world.combat.models import CreatureTemplate
from world.standoffs.models import CreatureDrive, FactionRule


class StandoffProfileForm(forms.ModelForm):
    """The creature template's own standoff fields: why it would fight, and its margin."""

    class Meta:
        model = CreatureTemplate
        fields = ["cause", "cause_margin_percent", "organization"]
        labels = {"organization": "Affiliation"}
        widgets = {
            "organization": AutocompleteSelect(
                CreatureTemplate._meta.get_field("organization"),  # noqa: SLF001
                admin.site,
            ),
        }
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
            "organization": (
                "Default organization. Its faction rules, its parents' and its society's apply "
                "to every placement unless a placement changes it."
            ),
        }


class CreatureDriveForm(forms.ModelForm):
    class Meta:
        model = CreatureDrive
        fields = ["property", "strength"]


class FactionRuleForm(forms.ModelForm):
    """One faction rule; ``rule`` is edited with the predicate rule widget (#4361)."""

    rule = PredicateRuleField(label="Test")

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
