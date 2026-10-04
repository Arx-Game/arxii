"""How a creature kind regards particular characters (regard rules)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db.models import F, Sum
from django.db.models.functions import Coalesce

from world.predicates.predicates import CharacterPredicateContext, matched_leaves
from world.societies.constants import COMMON_KNOWLEDGE_MULTIPLIER
from world.societies.models import LegendEntry

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.standoffs.models import CreatureDrive, RegardRule, StandoffGroup

DRIVE_MIN = 0
DRIVE_MAX = 3


@dataclass(frozen=True)
class MatchedRegard:
    """A regard rule that applies to a character, and the leaves that made it pass."""

    rule: RegardRule
    character_sheet: CharacterSheet
    reasons: list[dict]


def _has_common_knowledge_deed(sheet: CharacterSheet, archetype_id: int) -> bool:
    """True if one of the sheet's personas has a common-knowledge deed with the archetype.

    Same threshold as ``LegendEntry.is_common_knowledge`` and ``known_deed_ids``, as a
    query so no deed rows are walked in Python.
    """
    return (
        LegendEntry.objects.filter(
            persona__character_sheet=sheet,
            is_active=True,
            archetypes=archetype_id,
            base_value__gt=0,
        )
        .annotate(spread_total=Coalesce(Sum("spreads__value_added"), 0))
        .filter(spread_total__gte=(COMMON_KNOWLEDGE_MULTIPLIER - 1) * F("base_value"))
        .exists()
    )


def regard_matches(group: StandoffGroup, sheet: CharacterSheet) -> list[MatchedRegard]:
    """Every regard rule of the group's creature kind that applies to ``sheet``."""
    ctx = CharacterPredicateContext(sheet.character)
    matches: list[MatchedRegard] = []
    for rule in group.creature_template.regard_rules.all():
        reasons = matched_leaves(rule.rule, ctx)
        if reasons is None:
            continue
        if rule.deed_archetype_id is not None and not _has_common_knowledge_deed(
            sheet, rule.deed_archetype_id
        ):
            continue
        matches.append(MatchedRegard(rule=rule, character_sheet=sheet, reasons=reasons))
    return matches


def _active_sheets(group: StandoffGroup) -> list[CharacterSheet]:
    from world.combat.constants import ParticipantStatus  # noqa: PLC0415

    return [
        participant.character_sheet
        for participant in group.encounter.participants.filter(
            status=ParticipantStatus.ACTIVE
        ).select_related("character_sheet")
    ]


def suppressed_for_all_participants(group: StandoffGroup) -> bool:
    """True when every active participant matches a rule that suppresses the cause."""
    sheets = _active_sheets(group)
    if not sheets:
        return False
    return all(
        any(match.rule.suppresses_cause for match in regard_matches(group, sheet))
        for sheet in sheets
    )


def drive_strength_toward(group: StandoffGroup, drive: CreatureDrive, sheet: CharacterSheet) -> int:
    """The drive's strength toward this character after matched rules, clamped 0..3."""
    shift = sum(
        match.rule.drive_shift
        for match in regard_matches(group, sheet)
        if match.rule.drive_id == drive.property_id
    )
    return max(DRIVE_MIN, min(DRIVE_MAX, drive.strength + shift))


def band_shift_toward(group: StandoffGroup, sheet: CharacterSheet) -> int:
    """Total difficulty bands the group's regard rules add for this character."""
    return sum(match.rule.difficulty_shift_bands for match in regard_matches(group, sheet))
