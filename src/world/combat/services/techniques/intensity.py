"""Effective intensity for a technique or clash."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.models import CombatParticipant, CombatRoundAction
from world.magic.constants import EffectKind

if TYPE_CHECKING:
    from world.checks.types import ModifierContribution
    from world.magic.models import Technique
    from world.magic.types.magic_skills import CastCheck


def _sum_active_flat_bonuses(
    participant: CombatParticipant,
    *,
    technique: Technique,
    cast_check: CastCheck | None,
) -> int:
    """This round's committed FLAT_BONUS pull effects that relate to one use of ``technique``.

    A pull's bonus reaches only the uses its threads relate to (#5066): see
    ``round_pull_bonus``, which matches each effect's thread against this use by the
    test that decided what could be pulled.
    """
    from world.combat.pull_helpers import round_pull_bonus  # noqa: PLC0415

    return round_pull_bonus(
        participant,
        kind=EffectKind.FLAT_BONUS,
        technique_id=technique.pk,
        cast_check=cast_check,
    )


def compute_intensity_for_clash(
    participant: CombatParticipant,
    action: CombatRoundAction,
) -> int:
    """Return technique.intensity + related INTENSITY_BUMP pull bonuses for the clash floor gate.

    Used exclusively to gate the clash-open check (intensity_floor). Only pull effects
    whose threads relate to this action's technique count (#5066). Future
    intensity-ramp contributions (conditions, items, environment) can be added
    here and they will tighten the floor automatically.
    """
    from world.combat.pull_helpers import round_pull_bonus  # noqa: PLC0415
    from world.magic.services.magic_skills import resolve_cast_check  # noqa: PLC0415

    technique = action.focused_action
    if technique is None:
        return 0
    character = participant.character_sheet.character
    if not character.combat_pulls.active_for_encounter(participant.encounter):
        return technique.intensity  # no pull this round: no cast check to resolve
    pull_bonus = round_pull_bonus(
        participant,
        kind=EffectKind.INTENSITY_BUMP,
        technique_id=technique.pk,
        cast_check=resolve_cast_check(participant.character_sheet.character, technique),
    )
    return technique.intensity + pull_bonus


# ---------------------------------------------------------------------------
# Misses build intensity, and intensity adds to hit (#4858)
# ---------------------------------------------------------------------------


def is_attack_on_opponent(action: CombatRoundAction) -> bool:
    """Whether ``action``'s roll is an attack aimed at an opponent (#4858).

    Intensity helps attacks only: the to-hit bonus and the miss surge both ask this. A
    Strike, a technique or charge at an opponent, and a joust pass are attacks; a heal, a
    ward, a buff, or a cast at oneself or an ally is not.
    """
    from world.combat.constants import CombatManeuver  # noqa: PLC0415

    return action.focused_opponent_target_id is not None or action.maneuver == CombatManeuver.JOUST


def intensity_to_hit_contribution(
    participant: CombatParticipant, action: CombatRoundAction
) -> ModifierContribution | None:
    """What the attacker's engagement intensity adds to an attack roll, or None.

    Only an attack aimed at an opponent (``is_attack_on_opponent``) gains it. Each point
    of ``intensity_modifier`` on her COMBAT engagement for this encounter (the one a miss
    raises, ``combat_engagement_of``) adds "Intensity: to hit per point" (the maneuver
    effect catalog: its base plus modifiers scoped to that effect alone; a broad to-hit
    modifier is a flat bonus, not a rate). Nothing at 0 or below.
    """
    from world.checks.constants import ModifierSourceKind  # noqa: PLC0415
    from world.checks.types import ModifierContribution  # noqa: PLC0415
    from world.combat.constants import INTENSITY_MODIFIER_LABEL  # noqa: PLC0415
    from world.combat.dig_deep import combat_engagement_of  # noqa: PLC0415
    from world.mechanics.constants import ManeuverEffectKey  # noqa: PLC0415
    from world.mechanics.effect_targets import effect_modifier_total  # noqa: PLC0415
    from world.mechanics.maneuver_effects import get_maneuver_effect  # noqa: PLC0415

    if not is_attack_on_opponent(action):
        return None
    engagement = combat_engagement_of(participant)
    intensity = engagement.intensity_modifier if engagement is not None else 0
    if intensity <= 0:
        return None
    key = ManeuverEffectKey.INTENSITY_TO_HIT
    per_point = max(
        0,
        get_maneuver_effect(key).base_value
        + effect_modifier_total(participant.character_sheet, key, kind_wide=False),
    )
    if per_point <= 0:
        return None
    return ModifierContribution(
        source_kind=ModifierSourceKind.CHARACTER,
        source_label=INTENSITY_MODIFIER_LABEL,
        value=intensity * per_point,
    )


def is_miss(success_level: int | None) -> bool:
    """Whether an attack's hit roll missed: it failed (success level below 1).

    Read off the roll alone, never the damage table, so an empty damage-multiplier table
    does not turn every roll into a miss.
    """
    return (success_level or 0) < 1


def record_miss_intensity(participant: CombatParticipant) -> None:
    """A missed attack raises the attacker's intensity (#4858), once a round.

    The amount is "Miss: intensity gained" (the maneuver effect catalog, with her
    modifiers). Written through ``apply_dramatic_surge``, the one intensity seam: a MISSED
    surge for this round, with no room line. Nothing without a combat engagement here.
    """
    from world.combat.constants import SurgeTriggerKind  # noqa: PLC0415
    from world.combat.escalation import apply_dramatic_surge  # noqa: PLC0415
    from world.mechanics.constants import ManeuverEffectKey  # noqa: PLC0415
    from world.mechanics.effect_targets import effect_value  # noqa: PLC0415

    amount = effect_value(participant.character_sheet, ManeuverEffectKey.MISS_INTENSITY)
    if amount <= 0:
        return
    encounter = participant.encounter
    apply_dramatic_surge(
        encounter=encounter,
        participant=participant,
        amount=amount,
        trigger_kind=SurgeTriggerKind.MISSED,
        repeat_round=encounter.round_number,
        narrate=False,
        cause="A missed attack.",
    )
