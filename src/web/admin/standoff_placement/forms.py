"""Forms for the Placement page (#4361): one opponent line's edits over its template."""

from __future__ import annotations

from typing import Any

from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import AutocompleteSelect

from world.combat.constants import CauseKind
from world.mechanics.models import Property
from world.missions.models import MissionOptionOpponentLine
from world.standoffs.constants import DriveStrength
from world.standoffs.services.placement import DriveEdit, PlacementProfile
from world.stories.models import BeatOpponentLine

#: The "Here" pick that keeps the template's strength, and the one that removes the drive.
SAME = ""
REMOVE = "remove"
_LINE_FIELDS = ["cause_override", "cause_margin_override", "organization"]


def _cause_choices(template_cause: str) -> list[tuple[str, str]]:
    return [
        ("", f"(template: {CauseKind(template_cause).label})"),
        *CauseKind.choices,
    ]


class _LineForm(forms.ModelForm):
    """The line's own placement fields; the cause pick names the template's value."""

    def __init__(self, *args: Any, template_cause: str = CauseKind.NONE, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["cause_override"].choices = _cause_choices(template_cause)
        self.fields["cause_override"].label = "Cause"
        self.fields["cause_margin_override"].label = "Cause margin percent"
        self.fields["organization"].label = "Affiliation"
        template_org = self.instance.creature_template.organization
        self.fields["organization"].widget.attrs["data-placeholder"] = (
            f"(template: {template_org.name})" if template_org else "(template: no affiliation)"
        )
        self.fields["organization"].help_text = (
            "Blank keeps the template's affiliation. Another one brings that organization's "
            "rules, its parents' and its society's instead."
        )


class BeatLineForm(_LineForm):
    class Meta:
        model = BeatOpponentLine
        fields = ["opens_as_standoff", *_LINE_FIELDS]
        widgets = {
            "organization": AutocompleteSelect(
                BeatOpponentLine._meta.get_field("organization"),  # noqa: SLF001
                admin.site,
            ),
        }


class MissionLineForm(_LineForm):
    class Meta:
        model = MissionOptionOpponentLine
        fields = list(_LINE_FIELDS)
        widgets = {
            "organization": AutocompleteSelect(
                MissionOptionOpponentLine._meta.get_field("organization"),  # noqa: SLF001
                admin.site,
            ),
        }


def _strength_choices(template_label: str) -> list[tuple[str, str]]:
    return [
        (SAME, f"(same: {template_label})"),
        *((str(value), label) for value, label in DriveStrength.choices),
        (REMOVE, "Remove"),
    ]


class DrivesForm(forms.Form):
    """One "Here" pick per template drive: same, another strength, or removed."""

    def __init__(self, *args: Any, profile: PlacementProfile, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.profile = profile
        self.template_drives = [d for d in profile.drives if d.template_strength is not None]
        for drive in self.template_drives:
            if drive.strength is None:
                initial = REMOVE
            elif drive.strength == drive.template_strength:
                initial = SAME
            else:
                initial = str(drive.strength)
            self.fields[self.field_name(drive.property_id)] = forms.ChoiceField(
                choices=_strength_choices(drive.template_label),
                required=False,
                initial=initial,
                label=drive.property.name,
                widget=forms.Select(attrs={"aria-label": f"{drive.property.name} here"}),
            )

    @staticmethod
    def field_name(property_id: int) -> str:
        return f"drive_{property_id}"

    def rows(self) -> list[tuple[object, forms.BoundField]]:
        return [(drive, self[self.field_name(drive.property_id)]) for drive in self.template_drives]

    def edits(self) -> list[DriveEdit]:
        result = []
        for drive in self.template_drives:
            pick = self.cleaned_data.get(self.field_name(drive.property_id)) or SAME
            if pick == SAME:
                continue
            result.append(DriveEdit(drive.property, None if pick == REMOVE else int(pick)))
        return result


class AddedDriveForm(forms.Form):
    """A drive the template lacks, added for this placement only."""

    property = forms.ModelChoiceField(queryset=Property.objects.order_by("name"), label="Drive")
    strength = forms.TypedChoiceField(
        choices=DriveStrength.choices, coerce=int, initial=DriveStrength.MINOR
    )


AddedDriveFormSet = forms.formset_factory(AddedDriveForm, extra=0, can_delete=True)


class SuppressionsForm(forms.Form):
    """A switch-off box per inherited faction rule."""

    switched_off = forms.MultipleChoiceField(
        required=False, widget=forms.CheckboxSelectMultiple, label="Switch off here"
    )

    def __init__(self, *args: Any, profile: PlacementProfile, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.profile = profile
        self.fields["switched_off"].choices = [
            (str(entry.inherited.rule.pk), str(entry.inherited.rule.pk)) for entry in profile.rules
        ]
        if not self.is_bound:
            self.initial["switched_off"] = [
                str(entry.inherited.rule.pk) for entry in profile.rules if entry.suppressed
            ]

    def rule_ids(self) -> list[int]:
        return [int(pk) for pk in self.cleaned_data.get("switched_off", [])]

    def is_off(self, rule_pk: int) -> bool:
        current = (
            self.data.getlist(self.add_prefix("switched_off"))
            if self.is_bound
            else (self.initial.get("switched_off", []))
        )
        return str(rule_pk) in current
