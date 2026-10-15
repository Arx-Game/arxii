"""Read-only context for the Standoff Profile Builder's rail and drive table (#4354).

Everything here is computed from the saved rows, never written. The grade preview runs
the same ``social_target_difficulty`` the payload uses, for an example character of the
chosen level with no trait points beyond its level, against one example opponent of the
same level, with no faction rule matched.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from world.checks.constants import LEVEL_POINTS_PER_LEVEL
from world.checks.services import level_opposition
from world.checks.social_target import DriveHit, social_target_difficulty
from world.combat.constants import CauseKind
from world.combat.models import OpponentTierTemplate
from world.mechanics.models import Application
from world.mechanics.services import difficulty_indicator_for_rank_difference
from world.missions.models import MissionOptionOpponentLine
from world.standoffs.models import StandoffApproach, StandoffConfig, StandoffTerms
from world.stories.models import BeatOpponentLine
from world.traits.models import CheckRank

if TYPE_CHECKING:
    from world.checks.models import CheckType
    from world.combat.models import CreatureTemplate
    from world.standoffs.models import CreatureDrive

DEFAULT_PREVIEW_LEVEL = 5
DEFAULT_PREVIEW_PARTY = 4
MAX_PREVIEW = 50
_PERCENT = 100


@dataclass(frozen=True)
class DriveContext:
    """What a drive means and what reaches it, for its row in the drives table."""

    description: str
    hit_by: list[str]


@dataclass(frozen=True)
class PreviewLine:
    name: str
    grade: str
    grade_class: str
    note: str


@dataclass(frozen=True)
class Placement:
    label: str
    count: int
    opens_as_standoff: bool | None
    url: str = ""
    edited: bool = False


def _line_edited(line: object) -> bool:
    """True when a placement changes anything over its template (#4361)."""
    return bool(
        line.cause_override
        or line.cause_margin_override is not None
        or line.organization_id is not None
        or line.drive_edits.exists()
        or line.faction_rule_suppressions.exists()
    )


def drive_context(template: CreatureTemplate) -> dict[int, DriveContext]:
    """Per drive pk: the property's description and the approaches and terms that reach it."""
    drives = list(template.drives.select_related("property"))
    property_ids = [drive.property_id for drive in drives]
    approaches = list(StandoffApproach.objects.all())
    by_capability: dict[int, list[str]] = {}
    for approach in approaches:
        by_capability.setdefault(approach.capability_id, []).append(approach.name)
    reached: dict[int, list[str]] = {pid: [] for pid in property_ids}
    for capability_id, property_id in Application.objects.filter(
        capability_id__in=list(by_capability), target_property_id__in=property_ids
    ).values_list("capability_id", "target_property_id"):
        reached[property_id].extend(by_capability.get(capability_id, []))
    for terms in StandoffTerms.objects.filter(required_drive_id__in=property_ids):
        reached[terms.required_drive_id].append(f"terms {terms.name}")
    return {
        drive.pk: DriveContext(
            description=drive.property.description,
            hit_by=sorted(set(reached[drive.property_id])),
        )
        for drive in drives
    }


def _grade(check_type: CheckType | None, level: int, hits: list[DriveHit], bands: int) -> str:
    if check_type is None:
        return ""
    difficulty = social_target_difficulty(
        actor_sheet=None,
        target_character=None,
        check_type=check_type,
        target_level=level,
        drive_hits=hits,
        resist_increment=level_opposition(check_type, level=level),
        extra_bands=bands,
    ).difficulty
    rank_difference = CheckRank.get_rank_difference(LEVEL_POINTS_PER_LEVEL * level, difficulty)
    return difficulty_indicator_for_rank_difference(rank_difference).value


def _hits(drives: list[CreatureDrive], targeted: set[int]) -> list[DriveHit]:
    return [
        DriveHit(label=drive.property.name, strength=drive.strength)
        for drive in drives
        if drive.property_id in targeted
    ]


def grade_preview(template: CreatureTemplate, level: int) -> list[PreviewLine]:
    """Each approach and terms, graded for an example character against this creature."""
    from world.standoffs.services.view import grade_label  # noqa: PLC0415

    drives = list(template.drives.select_related("property"))
    approaches = list(StandoffApproach.objects.select_related("check_type"))
    targeted: dict[int, set[int]] = {}
    for capability_id, property_id in Application.objects.filter(
        capability_id__in=[a.capability_id for a in approaches],
        target_property_id__in=[d.property_id for d in drives],
    ).values_list("capability_id", "target_property_id"):
        targeted.setdefault(capability_id, set()).add(property_id)
    lines: list[PreviewLine] = []
    for approach in approaches:
        hits = _hits(drives, targeted.get(approach.capability_id, set()))
        grade = _grade(approach.check_type, level, hits, 0)
        note = ", ".join(f"hits {hit.label}, {hit.strength} band(s)" for hit in hits)
        lines.append(PreviewLine(approach.name, grade_label(grade), grade, note))
    config = StandoffConfig.load()
    drive_property_ids = {d.property_id for d in drives}
    for terms in StandoffTerms.objects.all():
        if terms.required_drive_id is not None and terms.required_drive_id not in (
            drive_property_ids
        ):
            continue
        grade = _grade(config.terms_check_type, level, [], terms.difficulty_shift_bands)
        lines.append(
            PreviewLine(
                f"Terms: {terms.name}",
                grade_label(grade) if grade else "no terms check set",
                grade,
                "listed once its drive is read" if terms.required_drive_id else "",
            )
        )
    return lines


def cause_check(
    template: CreatureTemplate,
    level: int,
    party: int,
    *,
    cause: str | None = None,
    margin: int | None = None,
) -> str:
    """A plain-text reading of the cause against an example party.

    ``cause`` and ``margin`` default to the template's own; the Placement page passes a
    placement's overrides (#4361).
    """
    cause = template.cause if cause is None else cause
    margin_percent = template.cause_margin_percent if margin is None else margin
    if cause == CauseKind.NONE:
        return "No cause: they never start a fight on their own."
    weight_row = OpponentTierTemplate.objects.filter(tier=template.tier).first()
    weight = weight_row.force_weight_percent if weight_row is not None else _PERCENT
    margin_factor = _PERCENT + margin_percent
    member_force = level * weight / _PERCENT
    party_force = party * level
    held_off = 0
    if member_force > 0:
        # The party holds them back while party * 100 > group * margin.
        held_off = max(0, int((party_force * _PERCENT - 1) // (member_force * margin_factor)))
    text = (
        f"With margin {margin_percent}, {party} level {level} characters hold "
        f"back up to {held_off} of them at level {level}; any more and the cause fires."
    )
    if cause == CauseKind.ORDERS:
        text += " Any botched press or terms against them also counts as a provocation."
    return text


def placements(template: CreatureTemplate) -> list[Placement]:
    """The beat and mission option lines that spawn this creature, linked to their pages."""
    from django.urls import reverse  # noqa: PLC0415

    rows = [
        Placement(
            f"Beat: {line.beat}",
            line.count,
            line.opens_as_standoff,
            url=reverse("admin_placement_beat", args=[line.pk]),
            edited=_line_edited(line),
        )
        for line in BeatOpponentLine.objects.filter(creature_template=template).select_related(
            "beat"
        )
    ]
    rows.extend(
        Placement(
            f"Mission option: {line.option}",
            line.count,
            None,
            url=reverse("admin_placement_mission", args=[line.pk]),
            edited=_line_edited(line),
        )
        for line in MissionOptionOpponentLine.objects.filter(
            creature_template=template
        ).select_related("option")
    )
    return rows


def preview_number(raw: str | None, default: int) -> int:
    """A small positive whole number from the preview's query string, else ``default``."""
    if raw and raw.isdigit():
        return max(1, min(MAX_PREVIEW, int(raw)))
    return default
