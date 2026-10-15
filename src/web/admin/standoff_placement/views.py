"""The Placement page (#4361): one opponent line, its edits over the template and the rules
it switches off.

Pattern: the Standoff Profile Builder. One page writes the line (``opens_as_standoff`` on a
beat line, the cause, margin and affiliation overrides), its ``OpponentLineDrive`` rows and
its ``OpponentLineFactionRuleSuppression`` rows in one transaction through the same
``save_placement`` the GM beat dialog uses, beside a rail: what will spawn, the beat's (or
mission's) level with a plain force check, and a note that GMs edit the same rows from the
story author. Reached from a beat's opponent lines (the inline's "Placement" link) and a
mission option line's change page (``links.builder_url``). Lines are not credited content.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms import BaseFormSet, ModelForm
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from web.admin.standoff_placement.forms import (
    AddedDriveFormSet,
    BeatLineForm,
    DrivesForm,
    MissionLineForm,
    SuppressionsForm,
)
from web.admin.standoff_profile import live as profile_live
from web.admin.tuning.views import superuser_required
from world.missions.models import MissionOptionOpponentLine
from world.standoffs.services.placement import (
    DriveEdit,
    PlacementProfile,
    draft_from_line,
    placement_profile,
    save_placement,
)
from world.stories.models import BeatOpponentLine

if TYPE_CHECKING:
    from world.standoffs.services.placement import OpponentLine

CONTINUE_BUTTON = "save_continue"
_DEFAULT_LEVEL = profile_live.DEFAULT_PREVIEW_LEVEL
_DEFAULT_PARTY = profile_live.DEFAULT_PREVIEW_PARTY


@dataclass
class _Forms:
    line: ModelForm
    drives: DrivesForm
    added: BaseFormSet
    rules: SuppressionsForm

    def is_valid(self) -> bool:
        return all(
            [
                self.line.is_valid(),
                self.drives.is_valid(),
                self.added.is_valid(),
                self.rules.is_valid(),
            ]
        )

    def drive_edits(self) -> list[DriveEdit]:
        added = [
            DriveEdit(form.cleaned_data["property"], form.cleaned_data["strength"])
            for form in self.added.forms
            if form.cleaned_data and not form.cleaned_data.get("DELETE")
        ]
        return [*self.drives.edits(), *added]


@dataclass(frozen=True)
class _Where:
    """Where the placement sits: its parent's name, links and example level."""

    label: str
    parent_label: str
    parent_url: str
    parent_changelist_label: str
    parent_changelist_url: str
    level: int
    level_note: str


def _beat_where(line: BeatOpponentLine) -> _Where:
    beat = line.beat
    beat_label = beat.internal_description.strip()[:60] or str(beat)
    level = beat.target_level or _DEFAULT_LEVEL
    note = (
        f"Target level {beat.target_level}."
        if beat.target_level
        else f"The beat has no target level; level {level} is an example."
    )
    return _Where(
        label=f'{line.creature_template.name} x{line.count} at "{beat_label}"',
        parent_label=beat_label,
        parent_url=reverse("admin:arxii_beat_change", args=[beat.pk]),
        parent_changelist_label="Beats",
        parent_changelist_url=reverse("admin:arxii_beat_changelist"),
        level=level,
        level_note=note,
    )


def _mission_where(line: MissionOptionOpponentLine) -> _Where:
    template = line.option.node.template
    level = max(1, (template.level_band_min + template.level_band_max) // 2)
    return _Where(
        label=f'{line.creature_template.name} x{line.count} at "{line.option}"',
        parent_label=str(line.option),
        parent_url=reverse("admin:arxii_missionoptionopponentline_change", args=[line.pk]),
        parent_changelist_label="Mission option opponent lines",
        parent_changelist_url=reverse("admin:arxii_missionoptionopponentline_changelist"),
        level=level,
        level_note=(
            f"The mission's level band is {template.level_band_min} to "
            f"{template.level_band_max}; level {level} is its middle."
        ),
    )


def _build_forms(request: HttpRequest, line: OpponentLine, profile: PlacementProfile) -> _Forms:
    data = request.POST if request.method == "POST" else None
    form_class = BeatLineForm if isinstance(line, BeatOpponentLine) else MissionLineForm
    added_initial = [
        {"property": drive.property, "strength": drive.strength}
        for drive in profile.drives
        if drive.template_strength is None and drive.strength
    ]
    return _Forms(
        line=form_class(data, instance=line, template_cause=line.creature_template.cause),
        drives=DrivesForm(data, profile=profile),
        added=AddedDriveFormSet(data, prefix="added", initial=added_initial or None),
        rules=SuppressionsForm(data, profile=profile),
    )


def _render(
    request: HttpRequest,
    line: OpponentLine,
    where: _Where,
    forms: _Forms,
    profile: PlacementProfile,
) -> HttpResponse:
    is_beat = isinstance(line, BeatOpponentLine)
    rule_rows = [(entry, forms.rules.is_off(entry.inherited.rule.pk)) for entry in profile.rules]
    return render(
        request,
        "admin/standoff_placement/page.html",
        {
            **admin.site.each_context(request),
            "is_nav_sidebar_enabled": False,
            "title": f"Placement: {where.label}",
            "line": line,
            "is_beat": is_beat,
            "where": where,
            "profile": profile,
            "form": forms.line,
            "drives": forms.drives,
            "added": forms.added,
            "rule_rows": rule_rows,
            "rules_form": forms.rules,
            "media": forms.line.media + forms.added.media,
            "summary": profile.summary(line.count),
            "cause_check": profile_live.cause_check(
                line.creature_template,
                where.level,
                _DEFAULT_PARTY,
                cause=profile.cause,
                margin=profile.cause_margin_percent,
            ),
            "party": _DEFAULT_PARTY,
            "builder_url": reverse("admin_standoff_profile", args=[line.creature_template.pk]),
        },
    )


def _page(request: HttpRequest, line: OpponentLine, where: _Where, page_url: str) -> HttpResponse:
    profile = placement_profile(line.creature_template, draft_from_line(line))
    forms = _build_forms(request, line, profile)
    if request.method != "POST":
        return _render(request, line, where, forms, profile)
    if forms.is_valid():
        try:
            with transaction.atomic():
                saved = forms.line.save()
                save_placement(
                    saved,
                    cause_override=saved.cause_override,
                    cause_margin_override=saved.cause_margin_override,
                    organization=saved.organization,
                    drive_edits=forms.drive_edits(),
                    suppressed_rule_ids=forms.rules.rule_ids(),
                )
        except ValidationError as exc:
            for message in exc.messages:
                forms.rules.add_error(None, message)
        else:
            messages.success(request, "Placement saved.")
            if CONTINUE_BUTTON in request.POST:
                return redirect(page_url)
            return redirect(where.parent_url)
    # Validating a ModelForm writes the posted values onto the identity-mapped line.
    line.flush_from_cache(force=True)
    return _render(request, line, where, forms, profile)


@superuser_required
def beat_line_placement(request: HttpRequest, line_pk: int) -> HttpResponse:
    """GET renders a beat opponent line's placement; POST saves it."""
    line = get_object_or_404(
        BeatOpponentLine.objects.select_related("beat", "creature_template"), pk=line_pk
    )
    return _page(request, line, _beat_where(line), reverse("admin_placement_beat", args=[line.pk]))


@superuser_required
def mission_line_placement(request: HttpRequest, line_pk: int) -> HttpResponse:
    """GET renders a mission option opponent line's placement; POST saves it."""
    line = get_object_or_404(
        MissionOptionOpponentLine.objects.select_related(
            "option__node__template", "creature_template"
        ),
        pk=line_pk,
    )
    return _page(
        request, line, _mission_where(line), reverse("admin_placement_mission", args=[line.pk])
    )
