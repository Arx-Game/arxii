"""Seed (or feed) a combat encounter from a hostile standalone technique cast.

When a PC casts a HOSTILE technique at another PC outside an existing fight, the
cast becomes the caster's opening combat declaration. This module wires that
intent into the existing combat lifecycle by REUSING the established services
(``add_participant`` / ``join_encounter`` / ``add_opponent`` /
``begin_declaration_phase`` / ``declare_action``). It builds no new combat
machinery — it only orchestrates the existing pieces and derives the target
opponent's stat kwargs from the target PC's CharacterSheet.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from django.db import transaction

from world.combat.constants import (
    EncounterStatus,
    EncounterType,
    OpponentTier,
    ParticipantStatus,
    RiskLevel,
)
from world.combat.models import CombatEncounter, CombatParticipant
from world.combat.services import (
    add_opponent,
    add_participant,
    begin_declaration_phase,
    declare_action,
    join_encounter,
)
from world.fatigue.constants import EffortLevel

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Technique
    from world.scenes.models import Scene


# A PC opponent is a real, competent foe rather than a mook/swarm; ELITE mirrors
# the PvP usage in the existing add_opponent tests.
_PVP_OPPONENT_TIER = OpponentTier.ELITE

# Fallback when the target sheet has no CharacterVitals row yet. A zero-HP
# opponent (PositiveIntegerField default) would be instantly defeated, so we
# floor at a sane combat value rather than invent precise stats.
_DEFAULT_MAX_HEALTH = 50


class _OpponentKwargs(TypedDict):
    name: str
    tier: str
    max_health: int
    threat_pool: None
    existing_objectdb: ObjectDB


def _opponent_kwargs_from_sheet(sheet: CharacterSheet) -> _OpponentKwargs:
    """Derive ``add_opponent`` stat kwargs for a PvP opponent from a PC's sheet.

    Pulls real values from the target's own data rather than inventing numbers:
    - ``name`` from the in-world character key.
    - ``max_health`` from the target's CharacterVitals (falls back to a sane
      positive default when no vitals row exists).
    - ``existing_objectdb`` is the target's Character ObjectDB (the PvP path —
      a pre-existing, non-ephemeral ObjectDB).
    - ``tier`` ELITE: a played character is a competent opponent.
    - ``threat_pool`` None: a PC opponent's actions are PC-declared, not driven
      by an NPC threat pool (the model FK is nullable).
    """
    vitals = getattr(sheet, "vitals", None)  # noqa: GETATTR_LITERAL
    max_health = (
        vitals.max_health if vitals is not None and vitals.max_health else _DEFAULT_MAX_HEALTH
    )
    return _OpponentKwargs(
        name=sheet.character.key,
        tier=_PVP_OPPONENT_TIER,
        max_health=max_health,
        threat_pool=None,
        existing_objectdb=sheet.character,
    )


def _caster_participant(
    encounter: CombatEncounter,
    caster_sheet: CharacterSheet,
) -> CombatParticipant:
    """Return the caster's active participant, creating/joining it if absent."""
    existing = CombatParticipant.objects.filter(
        encounter=encounter,
        character_sheet=caster_sheet,
        status=ParticipantStatus.ACTIVE,
    ).first()
    if existing is not None:
        return existing
    if encounter.status == EncounterStatus.DECLARING:
        # join_encounter is the PC self-join path; valid during DECLARING.
        return join_encounter(encounter, caster_sheet)
    return add_participant(encounter, caster_sheet)


@transaction.atomic
def seed_or_feed_encounter_from_cast(
    *,
    caster_sheet: CharacterSheet,
    target_sheet: CharacterSheet,
    technique: Technique,
    scene: Scene,
    room: ObjectDB,  # noqa: OBJECTDB_PARAM
) -> CombatEncounter:
    """Seed a new combat encounter from a hostile cast, or feed an active one.

    The cast becomes the caster's opening declaration for the current round, with
    the target PC represented as a PvP opponent (its own Character ObjectDB).

    Args:
        caster_sheet: The casting PC's sheet (becomes a participant).
        target_sheet: The targeted PC's sheet (becomes a PvP opponent).
        technique: The hostile (damage) technique driving the cast.
        scene: The Scene the cast happens in; the encounter binds to it.
        room: The room ObjectDB the encounter takes place in.

    Returns:
        The seeded or fed CombatEncounter, in DECLARING status with the caster's
        opening action declared.
    """
    encounter = CombatEncounter.objects.filter(
        scene=scene,
        status__in=[EncounterStatus.DECLARING, EncounterStatus.BETWEEN_ROUNDS],
    ).first()
    if encounter is None:
        encounter = CombatEncounter.objects.create(
            room=room,
            scene=scene,
            status=EncounterStatus.BETWEEN_ROUNDS,
            risk_level=RiskLevel.MODERATE,
            encounter_type=EncounterType.PARTY_COMBAT,
        )

    caster_participant = _caster_participant(encounter, caster_sheet)

    opponent = add_opponent(encounter, **_opponent_kwargs_from_sheet(target_sheet))

    if encounter.status == EncounterStatus.BETWEEN_ROUNDS:
        begin_declaration_phase(encounter)
        encounter.refresh_from_db()

    declare_action(
        caster_participant,
        focused_action=technique,
        focused_category=technique.action_category,
        effort_level=EffortLevel.MEDIUM,
        focused_opponent_target=opponent,
    )

    encounter.refresh_from_db()
    return encounter
