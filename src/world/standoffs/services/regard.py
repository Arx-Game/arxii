"""How a creature kind regards particular characters (regard rules)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db.models import F, Sum
from django.db.models.functions import Coalesce

from world.predicates.predicates import CharacterPredicateContext, matched_leaves
from world.scenes.services import active_persona_for_sheet
from world.societies.constants import COMMON_KNOWLEDGE_MULTIPLIER
from world.societies.models import LegendEntry

if TYPE_CHECKING:
    from collections.abc import Sequence

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
    """True if the persona the character is presenting has a common-knowledge deed.

    Only the presented persona counts (the primary when none is set); other personas
    are never read, so a deed under an alt cannot reveal the link to it.

    Same threshold as ``LegendEntry.is_common_knowledge`` and ``known_deed_ids``, as a
    query so no deed rows are walked in Python.
    """
    return (
        LegendEntry.objects.filter(
            persona=active_persona_for_sheet(sheet),
            is_active=True,
            archetypes=archetype_id,
            base_value__gt=0,
        )
        .annotate(spread_total=Coalesce(Sum("spreads__value_added"), 0))
        .filter(spread_total__gte=(COMMON_KNOWLEDGE_MULTIPLIER - 1) * F("base_value"))
        .exists()
    )


def regard_matches(
    group: StandoffGroup,
    sheet: CharacterSheet,
    rules: Sequence[RegardRule] | None = None,
) -> list[MatchedRegard]:
    """Every regard rule of the group's creature kind that applies to ``sheet``.

    ``rules`` lets a caller that checks many sheets fetch the group's rules once.
    """
    if rules is None:
        rules = list(group.creature_template.regard_rules.all())
    ctx = CharacterPredicateContext(sheet.character)
    matches: list[MatchedRegard] = []
    for rule in rules:
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
    rules = [r for r in group.creature_template.regard_rules.all() if r.suppresses_cause]
    return all(
        any(match.rule.suppresses_cause for match in regard_matches(group, sheet, rules))
        for sheet in sheets
    )


def drive_strength_from(matches: Sequence[MatchedRegard], drive: CreatureDrive) -> int:
    """The drive's strength after the given matched rules, clamped 0..3."""
    shift = sum(m.rule.drive_shift for m in matches if m.rule.drive_id == drive.property_id)
    return max(DRIVE_MIN, min(DRIVE_MAX, drive.strength + shift))


def band_shift_from(matches: Sequence[MatchedRegard]) -> int:
    """Total difficulty bands the given matched rules add."""
    return sum(m.rule.difficulty_shift_bands for m in matches)


def drive_strength_toward(group: StandoffGroup, drive: CreatureDrive, sheet: CharacterSheet) -> int:
    """The drive's strength toward this character after matched rules, clamped 0..3."""
    return drive_strength_from(regard_matches(group, sheet), drive)


def band_shift_toward(group: StandoffGroup, sheet: CharacterSheet) -> int:
    """Total difficulty bands the group's regard rules add for this character."""
    return band_shift_from(regard_matches(group, sheet))
