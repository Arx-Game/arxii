"""How a group stands toward particular characters (faction rules).

A group carries its template's rules and those inherited through its affiliation
(``services.profile.group_rules``). Rules test the character's presented persona, so
reputation and association leaves read the face the character is showing. Where two
matched rules shift the same thing (the difficulty, or one drive), the most specific
level wins: a template rule beats its organization's, which beats a parent's, which
beats a society's. Rules at the same level add up (#4361).
"""

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
    from collections.abc import Callable, Sequence

    from world.character_sheets.models import CharacterSheet
    from world.standoffs.models import FactionRule, StandoffGroup
    from world.standoffs.services.profile import GroupDrive, InheritedRule

DRIVE_MIN = 0
DRIVE_MAX = 3


@dataclass(frozen=True)
class MatchedFactionRule:
    """A faction rule that applies to a character, and the leaves that made it pass."""

    rule: FactionRule
    character_sheet: CharacterSheet
    reasons: list[dict]
    level: int = 0
    source: str = ""


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


def faction_rule_matches(
    group: StandoffGroup,
    sheet: CharacterSheet,
    rules: Sequence[InheritedRule] | None = None,
) -> list[MatchedFactionRule]:
    """Every faction rule the group carries that applies to ``sheet``.

    ``rules`` lets a caller that checks many sheets fetch the group's rules once.
    """
    if rules is None:
        from world.standoffs.services.profile import group_rules  # noqa: PLC0415

        rules = group_rules(group)
    ctx = CharacterPredicateContext(
        sheet.character, presented_persona=active_persona_for_sheet(sheet)
    )
    matches: list[MatchedFactionRule] = []
    for entry in rules:
        rule = entry.rule
        reasons = matched_leaves(rule.rule, ctx)
        if reasons is None:
            continue
        if rule.deed_archetype_id is not None and not _has_common_knowledge_deed(
            sheet, rule.deed_archetype_id
        ):
            continue
        matches.append(
            MatchedFactionRule(
                rule=rule,
                character_sheet=sheet,
                reasons=reasons,
                level=entry.level,
                source=entry.source,
            )
        )
    return matches


def _active_sheets(group: StandoffGroup) -> list[CharacterSheet]:
    from world.combat.constants import ParticipantStatus  # noqa: PLC0415

    return [
        participant.character_sheet
        for participant in group.encounter.participants.filter(
            status=ParticipantStatus.ACTIVE
        ).select_related("character_sheet")
    ]


def cause_effect_from(matches: Sequence[MatchedFactionRule]) -> str:
    """What the matched rules do to the group's cause for one character (#4415).

    The most specific level holding a rule with an effect decides; at that level a Provoke
    beats a Suppress. None when no matched rule has an effect.
    """
    from world.standoffs.constants import CauseEffect  # noqa: PLC0415

    with_effect = [m for m in matches if m.rule.cause_effect != CauseEffect.NONE]
    if not with_effect:
        return CauseEffect.NONE
    level = min(m.level for m in with_effect)
    effects = {m.rule.cause_effect for m in with_effect if m.level == level}
    return CauseEffect.PROVOKE if CauseEffect.PROVOKE in effects else CauseEffect.SUPPRESS


@dataclass(frozen=True)
class CauseEffects:
    """How the group's faction rules bear on its cause for the active participants.

    ``provoked_by`` is the sheet of the first participant whose rules provoke the group
    (None when nobody does); ``suppressed`` is True when every active participant's rules
    suppress it.
    """

    provoked_by: CharacterSheet | None
    suppressed: bool


def cause_effects(group: StandoffGroup) -> CauseEffects:
    """The cause effects of the group's faction rules over its active participants."""
    from world.standoffs.constants import CauseEffect  # noqa: PLC0415
    from world.standoffs.services.profile import group_rules  # noqa: PLC0415

    sheets = _active_sheets(group)
    rules = [entry for entry in group_rules(group) if entry.rule.cause_effect != CauseEffect.NONE]
    if not sheets or not rules:
        return CauseEffects(provoked_by=None, suppressed=False)
    effects = [
        (sheet, cause_effect_from(faction_rule_matches(group, sheet, rules))) for sheet in sheets
    ]
    provoked_by = next((sheet for sheet, effect in effects if effect == CauseEffect.PROVOKE), None)
    suppressed = all(effect == CauseEffect.SUPPRESS for _, effect in effects)
    return CauseEffects(provoked_by=provoked_by, suppressed=suppressed)


def _most_specific_total(
    matches: Sequence[MatchedFactionRule], value: Callable[[FactionRule], int]
) -> int:
    """Sum ``value`` over the matched rules at the most specific level that shifts it."""
    by_level: dict[int, int] = {}
    for match in matches:
        amount = value(match.rule)
        if amount:
            by_level[match.level] = by_level.get(match.level, 0) + amount
    return by_level[min(by_level)] if by_level else 0


def _winning_ids(
    matches: Sequence[MatchedFactionRule], value: Callable[[FactionRule], int]
) -> set[int]:
    shifting = [m for m in matches if value(m.rule)]
    if not shifting:
        return set()
    level = min(m.level for m in shifting)
    return {m.rule.pk for m in shifting if m.level == level}


def shifting_rule_ids(
    matches: Sequence[MatchedFactionRule], targeted_property_ids: set[int]
) -> set[int]:
    """The matched rules that actually shift a roll aimed at ``targeted_property_ids``.

    The rules counted for the difficulty, plus, for each targeted drive, the rules counted
    for that drive's strength. A rule outranked by a more specific one does not count,
    even when its drive shift took the drive's strength to zero.
    """
    ids = _winning_ids(matches, lambda rule: rule.difficulty_shift_bands)
    for property_id in targeted_property_ids:
        ids |= _winning_ids(
            matches, lambda rule, pid=property_id: rule.drive_shift if rule.drive_id == pid else 0
        )
    return ids


def drive_strength_from(matches: Sequence[MatchedFactionRule], drive: GroupDrive) -> int:
    """The drive's strength after the given matched rules, clamped 0..3."""
    shift = _most_specific_total(
        matches, lambda rule: rule.drive_shift if rule.drive_id == drive.property_id else 0
    )
    return max(DRIVE_MIN, min(DRIVE_MAX, drive.strength + shift))


def band_shift_from(matches: Sequence[MatchedFactionRule]) -> int:
    """Difficulty bands the given matched rules add (the most specific level that shifts)."""
    return _most_specific_total(matches, lambda rule: rule.difficulty_shift_bands)


def drive_strength_toward(group: StandoffGroup, drive: GroupDrive, sheet: CharacterSheet) -> int:
    """The drive's strength toward this character after matched rules, clamped 0..3."""
    return drive_strength_from(faction_rule_matches(group, sheet), drive)


def band_shift_toward(group: StandoffGroup, sheet: CharacterSheet) -> int:
    """Difficulty bands the group's faction rules add for this character."""
    return band_shift_from(faction_rule_matches(group, sheet))


@dataclass(frozen=True)
class RuleTest:
    """One faction rule run against one character, for staff (the Faction Rules page)."""

    rule: FactionRule
    source: str
    inherited: bool
    matched: bool
    reasons: list[str]


def run_rules_against(
    sheet: CharacterSheet, entries: Sequence[InheritedRule], own_level: int
) -> list[RuleTest]:
    """Run each rule against ``sheet`` as presented now and say why it matched.

    Staff-only: the reasons name the hidden reputation tier and the association behind a
    match (``explain_leaf_for_staff``), which a player never sees. ``own_level`` is the
    precedence level of the page's own rules; any other level is inherited.
    """
    from world.predicates.describe import explain_leaf_for_staff  # noqa: PLC0415

    persona = active_persona_for_sheet(sheet)
    ctx = CharacterPredicateContext(sheet.character, presented_persona=persona)
    results: list[RuleTest] = []
    for entry in entries:
        rule = entry.rule
        leaves = matched_leaves(rule.rule, ctx)
        matched = leaves is not None and (
            rule.deed_archetype_id is None
            or _has_common_knowledge_deed(sheet, rule.deed_archetype_id)
        )
        reasons = [explain_leaf_for_staff(leaf, persona) for leaf in (leaves or [])]
        if matched and rule.deed_archetype_id is not None:
            reasons.append(f"known for {rule.deed_archetype.name} deeds")
        results.append(
            RuleTest(
                rule=rule,
                source=entry.source,
                inherited=entry.level != own_level,
                matched=matched,
                reasons=reasons if matched else [],
            )
        )
    return results
