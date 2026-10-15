"""Forms for the Faction Rules page (#4361): an organization's or a society's rules."""

from __future__ import annotations

from django import forms
from django.forms import inlineformset_factory

from web.admin.standoff_profile.forms import FactionRuleForm
from world.societies.models import Organization, Society
from world.standoffs.models import FactionRule

OrganizationRuleFormSet = inlineformset_factory(
    Organization,
    FactionRule,
    form=FactionRuleForm,
    fk_name="organization",
    extra=0,
    can_delete=True,
)

SocietyRuleFormSet = inlineformset_factory(
    Society,
    FactionRule,
    form=FactionRuleForm,
    fk_name="society",
    extra=0,
    can_delete=True,
)


class CharacterTestForm(forms.Form):
    """The rail's "test a character" picker: a character's name, as staff know it."""

    character = forms.CharField(
        required=False,
        max_length=200,
        label="Character",
        help_text="The character's name or the name they present under.",
    )
