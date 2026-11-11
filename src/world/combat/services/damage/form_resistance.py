"""A form's resistance is paid and rolled on every blow it softens (#5066 decision 18).

A technique that turns her into smoke (or any form that shrugs off blows) is a condition
it put on its own caster carrying a positive ``ConditionResistanceModifier``. The
resistance is not a standing buff: each blow it softens is a use of the form's technique,
cast as the blow lands (``use_technique``: its anima through the deficit and Soulfray
path), and the roll scales that condition's authored resistance for this blow: a failure
softens nothing, a bare success the authored amount, each level above adds
``MovementConfig.strength_per_success_level_percent`` of it (``scaled_strength``, as a
movement use's strength). Her "dodge even into Soulfray" answer is the cast's consent, and
a blow she did not choose is never lethal for a player who is not connected.

Any other resistance (a species vulnerability, armor-like conditions, a ward an ally cast, a
passive's condition, a price's inflicted condition, a condition a covenant vow's added
effect put on her while riding her cast, gift threads and every other thread's standing
tier-0 bonus) stays flat and free in ``resolve_damage_type_resistance``: those are her
baseline, always there (maintainer, 2026-11-11). So does the form's own resistance outside a blow:
damage-over-time ticks, hazards and battle damage read it flat, with no cast. Only player
characters' blows reach this (``apply_damage_to_participant``); an NPC's resistance is flat.

Revisit note (maintainer, decision 18): if paying per blow makes barrier and mitigation
types too weak against swarms or area attacks, consider paying them by damage absorbed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.combat.models import CombatParticipant
    from world.conditions.models import ConditionInstance, DamageType


@dataclass(frozen=True)
class FormBlow:
    """One form softening one blow: its authored resistance and what the roll made of it."""

    instance: ConditionInstance
    authored: int
    softened: int
    anima_paid: int


def paid_per_blow(instance: ConditionInstance, character_pk: int) -> bool:
    """Whether ``instance`` is a form whose resistance is a cast on each blow (#5066
    decision 18, maintainer ruling 2026-11-11): a condition a technique she CAST put on
    herself, one of that technique's own authored applied conditions. Not a passive's
    condition (applied with no roll), not the condition a personal price inflicts on its
    payer (a drawback she chose, not a buff), and not a condition a covenant vow's added
    effect applied while riding the cast: it carries the cast technique as provenance but
    is not the technique's own, and vow defenses are free (maintainer, 2026-11-11)."""
    from world.combat.services.damage.passive_techniques import (  # noqa: PLC0415
        PASSIVE_SOURCE_PREFIX,
    )

    if instance.source_technique_id is None or instance.source_character_id != character_pk:
        return False
    if instance.source_description.startswith(PASSIVE_SOURCE_PREFIX):
        return False
    if not _is_technique_own_condition(instance):
        return False
    return not _is_price_condition(instance)


def _is_technique_own_condition(instance: ConditionInstance) -> bool:
    """Whether the technique that applied ``instance`` authors that condition itself."""
    from world.magic.models import TechniqueAppliedCondition  # noqa: PLC0415

    return TechniqueAppliedCondition.objects.filter(
        technique_id=instance.source_technique_id, condition_id=instance.condition_id
    ).exists()


def _is_price_condition(instance: ConditionInstance) -> bool:
    """Whether ``instance`` is what her hold's price inflicts for paying it."""
    from world.magic.models import CharacterTechnique  # noqa: PLC0415

    return CharacterTechnique.objects.filter(
        character_id=instance.source_character_id,
        technique_id=instance.source_technique_id,
        price__inflicted_condition_id=instance.condition_id,
    ).exists()


def forms_softening(
    participant: CombatParticipant, damage_type: DamageType | None
) -> list[tuple[ConditionInstance, int]]:
    """Her forms with a positive resistance against ``damage_type``, and that resistance."""
    from world.conditions.handlers import _instance_resistance_modifier  # noqa: PLC0415
    from world.conditions.services import resolved_damage_type  # noqa: PLC0415

    damage_type = resolved_damage_type(damage_type)
    if damage_type is None:
        return []
    character = participant.character_sheet.character
    found = []
    for instance in character.conditions._active:  # noqa: SLF001 - the prefetched list
        if not paid_per_blow(instance, character.pk):
            continue
        value = _instance_resistance_modifier(instance, damage_type)
        if value > 0:
            found.append((instance, value))
    return found


def cast_forms_for_blow(
    participant: CombatParticipant, damage_type: DamageType | None
) -> list[FormBlow]:
    """Cast each form once for this blow; what each softened. Empty when she has none."""
    from world.combat.services.movement_use import use_technique_for_strength  # noqa: PLC0415

    blows = []
    character = participant.character_sheet.character
    for instance, authored in forms_softening(participant, damage_type):
        use = use_technique_for_strength(
            character,
            instance.source_technique,
            base_value=authored,
            participant=participant,
            lethal=participant.encounter.is_lethal,
            confirm_soulfray_risk=participant.dodge_into_soulfray,
            chosen_by_player=False,
        )
        blows.append(
            FormBlow(
                instance=instance,
                authored=authored,
                softened=use.strength if use.went_off else 0,
                anima_paid=use.anima_paid,
            )
        )
    return blows


def resistance_shift_for(blows: list[FormBlow]) -> int:
    """How much less resistance this blow meets than the flat sum counts: each form's
    authored amount, less what its roll softened."""
    return sum(blow.authored - blow.softened for blow in blows)
