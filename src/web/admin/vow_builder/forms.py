"""Forms for the vow page (#4880, slice 2 of #4843).

One vow is a ``CovenantRole`` with its technique specialties, its focus picks and each
pick's limits. Payload rows (added effects, situational perks, stat scalings) are not
edited here: the page links each to its stock admin form in the admin popup.
"""

from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory
from django.http import QueryDict

from world.admin_utils import OneRowPerFormSet
from world.covenants.models import (
    CovenantRole,
    CovenantRoleTechniqueSpecialty,
    VowAddedEffect,
    VowFocusPick,
    VowFocusPickLimit,
    VowSituationalPerk,
    VowStatScaling,
)

#: The vow's own fields the page edits; ``slug`` is shown, never edited, since code reads it.
VOW_FIELDS: tuple[str, ...] = (
    "name",
    "covenant_type",
    "description",
    "parent_role",
    "resonance",
    "speed_rank",
    "sword_weight",
    "shield_weight",
    "crown_weight",
    "command_tier",
    "is_champion_role",
    "grants_insight",
    "calls_out_windups",
    "prepares_ground",
    "reveals_weakness",
    "enhances_assessment",
)

#: The boolean flags, drawn together as one row of checkboxes.
VOW_FLAG_FIELDS: tuple[str, ...] = (
    "is_champion_role",
    "grants_insight",
    "calls_out_windups",
    "prepares_ground",
    "reveals_weakness",
    "enhances_assessment",
)


class VowForm(forms.ModelForm):
    """The vow's own fields. ``parent_role`` lists primary roles other than this one."""

    class Meta:
        model = CovenantRole
        fields = VOW_FIELDS
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        parents = CovenantRole.objects.filter(parent_role__isnull=True).order_by("name")
        if self.instance.pk is not None:
            parents = parents.exclude(pk=self.instance.pk)
        self.fields["parent_role"].queryset = parents


SpecialtyFormSet = inlineformset_factory(
    CovenantRole,
    CovenantRoleTechniqueSpecialty,
    formset=OneRowPerFormSet,
    fields=("function", "multiplier_tenths"),
    extra=0,
    can_delete=True,
)


class _PickBaseFormSet(OneRowPerFormSet):
    """Refuses deleting a pick that still has payload rows.

    A payload row's ``focus_pick`` is RESTRICT: the database would refuse the delete
    part way through the save, so the page names the pick and the rows instead.
    """

    def clean(self) -> None:
        super().clean()
        deleting = {
            form.instance.pk: form.instance.name
            for form in self.forms
            if form.instance.pk is not None and form.cleaned_data.get("DELETE")
        }
        with_payload = _picks_with_payload(set(deleting))
        blocked = [name for pk, name in deleting.items() if pk in with_payload]
        if blocked:
            raise ValidationError(
                [
                    f"'{name}' still has payload rows. Delete them from its edit links first."
                    for name in blocked
                ]
            )


def _picks_with_payload(pick_ids: set[int]) -> set[int]:
    """Which of ``pick_ids`` still carry a payload row: three queries, none when empty."""
    if not pick_ids:
        return set()
    found: set[int] = set()
    for model in (VowAddedEffect, VowSituationalPerk, VowStatScaling):
        found.update(
            model.objects.filter(focus_pick_id__in=pick_ids).values_list("focus_pick_id", flat=True)
        )
    return found


PickFormSet = inlineformset_factory(
    CovenantRole,
    VowFocusPick,
    formset=_PickBaseFormSet,
    fk_name="covenant_role",
    fields=("pick_level", "name", "value", "description"),
    widgets={"description": forms.Textarea(attrs={"rows": 2})},
    extra=0,
    can_delete=True,
)

LimitFormSet = inlineformset_factory(
    VowFocusPick,
    VowFocusPickLimit,
    formset=OneRowPerFormSet,
    fields=("kind", "frequency_tenths", "reduction", "description"),
    widgets={"description": forms.TextInput()},
    extra=0,
    can_delete=True,
)


def limit_formset_for(pick: VowFocusPick, data: QueryDict | None = None) -> LimitFormSet:
    """One saved pick's limits formset, prefixed ``l<pick.pk>``.

    An unsaved pick has no limits formset: the page asks for the pick to be saved first.
    """
    return LimitFormSet(data, instance=pick, prefix=f"l{pick.pk}")
