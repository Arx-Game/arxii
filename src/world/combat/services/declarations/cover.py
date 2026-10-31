"""Declaring cover and applying position cover."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import CombatManeuver, OpponentStatus, ParticipantStatus
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    CombatRoundAction,
)
from world.fatigue.constants import EffortLevel
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from typeclasses.characters import Character
    from world.areas.positioning.models import Position
    from world.conditions.models import DamageType


def declare_cover(
    participant: CombatParticipant,
    ally: CombatParticipant,
) -> CombatRoundAction:
    """Declare a covering maneuver for an ally -- passives-only, auto-ready.

    Cover resolves as a no-op on its own; its effect is the coverer's
    Cover escape bonus (the maneuver effect catalog), which it contributes to the ally's
    flee check in _resolve_flee.
    Covering an ally who never declares flee simply wastes the action.
    """
    from world.vitals.services import is_dead  # noqa: PLC0415

    encounter = participant.encounter
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot cover: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    if participant.status != ParticipantStatus.ACTIVE:
        msg = "Cannot cover: participant is no longer active in this encounter."
        raise ValueError(msg)

    if is_dead(participant.character_sheet):
        msg = "Cannot cover: character is dead."
        raise ValueError(msg)
    if ally.pk == participant.pk:
        msg = "Cannot cover yourself."
        raise ValueError(msg)
    if ally.encounter_id != encounter.pk or ally.status != ParticipantStatus.ACTIVE:
        msg = "Cover target must be an active participant in this encounter."
        raise ValueError(msg)
    action, _ = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": None,
            "focused_category": None,
            "effort_level": EffortLevel.VERY_LOW,
            "focused_opponent_target": None,
            "focused_ally_target": ally,
            "maneuver": CombatManeuver.COVER,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": True,
        },
    )
    return action


def _combatants_at_position(
    encounter: CombatEncounter,
    position: Position,
) -> list[ObjectDB]:  # noqa: OBJECTDB_PARAM
    """Every ACTIVE participant's character + ACTIVE opponent's objectdb at *position*.

    Single query against ``position.occupants`` (the ``ObjectPosition`` reverse
    relation) rather than calling ``current_position`` per combatant, to avoid a
    query-in-a-loop over the encounter's roster.
    """
    occupant_ids = set(position.occupants.values_list("objectdb_id", flat=True))

    characters: list[ObjectDB] = [
        p.character_sheet.character
        for p in CombatParticipant.objects.filter(
            encounter=encounter, status=ParticipantStatus.ACTIVE
        ).select_related("character_sheet__character")
        if p.character_sheet.character_id in occupant_ids
    ]
    characters.extend(
        opp.objectdb
        for opp in CombatOpponent.objects.filter(
            encounter=encounter, status=OpponentStatus.ACTIVE
        ).select_related("objectdb")
        if opp.objectdb_id is not None and opp.objectdb_id in occupant_ids
    )
    return characters


def apply_position_cover(character: Character, damage: int, damage_type: DamageType | None) -> int:
    """Subtract attack-cover from damage.

    Reads the character's current position and sums PositionShelter rows with
    applies_to_attacks=True for the given damage type. No-op when the character
    is unpositioned (lenient — matching technique_can_reach) or when damage_type
    is None. Combat seams resolve untyped damage to Physical first (#4742), so None
    reaches here only when no Physical row is configured.

    Args:
        character: The target character taking damage.
        damage: The incoming damage amount (after armor soak, before condition interactions).
        damage_type: The incoming attack's damage type (None only with no Physical row set).

    Returns:
        The damage after cover reduction, floored at 0.
    """
    if damage <= 0 or damage_type is None:
        return damage
    from world.areas.positioning.services import (  # noqa: PLC0415
        position_of,
        position_shelter_value,
    )

    position = position_of(character)
    if position is None:
        return damage
    cover = position_shelter_value(position, damage_type, attacks_only=True)
    return max(0, damage - cover)
