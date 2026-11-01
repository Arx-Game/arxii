"""A PC's defense roll against an NPC blow, recorded and laid out as rows (#4884).

``resolve_npc_attack`` records the defender's roll as one ``ConsequenceOutcome`` on the NPC
action's Narrator ACTION interaction (``create_npc_action_interaction``, the anchor the
survivability rolls already use), for the defender's own character. Everything the
breakdown names is kept at roll time: who the blow came from, the defense skill's rating,
the combat style's name, skill rating or lapse reason, and its armor share. A later change
to the character, the style or the opponent never rewrites the record.

The breakdown follows demo screen 5, "Defending in plate": a heading naming the attacker,
the defense skill and its rating, the style skill (or the style struck through with the
reason it lapsed), "Armor, N of 10" with "the style's armor share" when the defender has a
style, then the result. A barrier's re-roll of the same check is not recorded: one roll,
one row.

A row is a defense roll when ``against_label`` is set; nothing else writes it, so this
builder and ``strike_roll_breakdowns`` (keyed on a Strike's round action) never claim the
same row.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import DEFENSE_REDUCED_THRESHOLD

if TYPE_CHECKING:
    from collections.abc import Sequence

    from world.checks.models import CheckType
    from world.checks.outcome_models import ConsequenceOutcome
    from world.checks.types import ModifierBreakdown, RollBreakdown
    from world.combat.models import CombatParticipant
    from world.covenants.style_fit import StyleFit
    from world.scenes.models import Interaction


def defense_result_line(success_level: int | None, damage: int) -> str:
    """The defense roll's result line: "Defended, no damage", "Partly defended, 4 damage"
    or "Hit, 8 damage"."""
    level = success_level or 0
    if damage <= 0:
        return "Defended, no damage"
    if level >= DEFENSE_REDUCED_THRESHOLD:
        return f"Partly defended, {damage} damage"
    return f"Hit, {damage} damage"


def _defense_skill_rating(participant: CombatParticipant, check_type: CheckType) -> int | None:
    """The defender's rating in the skill ``check_type`` weights, now; None with no skill."""
    from world.combat.services.declarations.strike import strike_check_traits  # noqa: PLC0415
    from world.traits.models import CharacterTraitValue  # noqa: PLC0415

    skill, _stats = strike_check_traits({check_type.pk})[check_type.pk]
    if skill is None:
        return None
    return (
        CharacterTraitValue.objects.filter(character=participant.character_sheet, trait__name=skill)
        .values_list("value", flat=True)
        .first()
    ) or 0


def _style_skill_rating(participant: CombatParticipant, style_fit: StyleFit) -> int | None:
    from world.traits.models import CharacterTraitValue  # noqa: PLC0415

    if not style_fit.counts:
        return None
    return (
        CharacterTraitValue.objects.filter(
            character=participant.character_sheet, trait_id=style_fit.style.skill.trait_id
        )
        .values_list("value", flat=True)
        .first()
    ) or 0


def record_defense_roll(  # noqa: PLR0913 - one record, its parts
    participant: CombatParticipant,
    *,
    attacker_name: str,
    check_type: CheckType,
    breakdown: ModifierBreakdown,
    style_fit: StyleFit,
    summary: str,
    interaction: Interaction,
) -> ConsequenceOutcome:
    """Record ``participant``'s defense roll on the NPC action's ``interaction``."""
    from world.checks.services import record_consequence_outcome  # noqa: PLC0415
    from world.checks.types import RollSnapshot  # noqa: PLC0415

    style = style_fit.style
    has_style_term = style_fit.has_skill_term
    snapshot = RollSnapshot(
        weapon_label="",
        weapon_kind="",
        stat_label="",
        style_name=style.name if has_style_term else "",
        style_skill_rating=_style_skill_rating(participant, style_fit),
        style_lapse_note=style_fit.lapse_note if has_style_term else "",
        against_label=attacker_name,
        armor_share_tenths=style.armor_share_tenths if style is not None else None,
    )
    return record_consequence_outcome(
        participant.character_sheet,
        check_type,
        None,
        None,
        breakdown,
        combat_interaction=interaction,
        summary=summary[:255],
        skill_rating=_defense_skill_rating(participant, check_type),
        snapshot=snapshot,
    )


def defense_roll_breakdowns(outcomes: Sequence[ConsequenceOutcome]) -> dict[int, RollBreakdown]:
    """The rows of each defense roll among ``outcomes``, keyed by outcome pk.

    One query (the check types' skills) when any defense roll is present, none otherwise.
    """
    from world.checks.types import RollBreakdown, RollLine  # noqa: PLC0415
    from world.combat.services.declarations.strike import (  # noqa: PLC0415
        strike_check_traits,
        style_roll_line,
    )

    defenses = [o for o in outcomes if o.against_label]
    if not defenses:
        return {}
    traits = strike_check_traits({o.check_type_id for o in defenses})
    breakdowns: dict[int, RollBreakdown] = {}
    for o in defenses:
        skill, _stats = traits[o.check_type_id]
        lines: list[RollLine] = []
        if skill is not None:
            rating = str(o.skill_rating) if o.skill_rating is not None else ""
            lines.append(RollLine(skill, rating, "defense skill"))
        style_line = style_roll_line(o)
        if style_line is not None:
            lines.append(style_line)
        if o.armor_share_tenths is not None:
            lines.append(
                RollLine(f"Armor, {o.armor_share_tenths} of 10", "", "the style's armor share")
            )
        breakdowns[o.pk] = RollBreakdown(
            heading=f"Defense against {o.against_label}", lines=lines, result=o.summary
        )
    return breakdowns
