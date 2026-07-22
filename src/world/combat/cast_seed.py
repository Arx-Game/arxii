"""Seed (or feed) a combat encounter from a hostile standalone technique cast.

When a PC casts a HOSTILE technique at another PC outside an existing fight, the
cast becomes the caster's opening combat declaration. This module wires that
intent into the existing combat lifecycle by REUSING the established services
(``add_participant`` / ``join_encounter`` / ``add_opponent`` /
``begin_declaration_phase`` / ``declare_action`` / ``acknowledge_encounter_risk``),
deriving the target opponent's stat kwargs from the target PC's CharacterSheet.
It also owns the cast-side risk gate (#777):
``encounter_requiring_risk_acknowledgement`` decides whether a hostile cast must
pause for the target's consent before feeding a high-risk encounter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from django.db import transaction

from world.combat.beat_wiring import activate_stakes_for_scene
from world.combat.chosen_ground import compute_on_chosen_ground
from world.combat.constants import (
    RISK_LEVELS_REQUIRING_ACKNOWLEDGEMENT,
    CombatAllegiance,
    EncounterType,
    OpponentStatus,
    OpponentTier,
    ParticipantStatus,
    RiskLevel,
)
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    EncounterRiskAcknowledgement,
)
from world.combat.services import (
    acknowledge_encounter_risk,
    add_opponent,
    add_participant,
    begin_declaration_phase,
    declare_action,
    join_encounter,
)
from world.fatigue.constants import EffortLevel
from world.scenes.constants import RoundStatus
from world.scenes.models import Scene

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Technique


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
    vitals = sheet.vitals_or_none
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


def _scene_is_active_non_battle(scene: Scene) -> bool:
    """True when *scene* is itself an active, non-Battle-backed Scene.

    Mirrors the classification ``world.covenants.perks.evaluators.during_negotiation``
    documents (``Scene.objects.active_for_room``'s ``is_active`` + ``battle__isnull``
    filter, #2010) — scoped directly to this scene by pk rather than re-derived from a
    room, since the caller already holds the ``Scene`` in hand (no location lookup
    needed). Feeds ``CombatEncounter.opened_from_parley`` (#2536 slice 3, Task 4). One
    query.
    """
    return Scene.objects.filter(pk=scene.pk, is_active=True, battle__isnull=True).exists()


def _feedable_encounter(scene: Scene) -> CombatEncounter | None:
    """The scene's encounter a cast can feed (DECLARING or BETWEEN_ROUNDS), if any."""
    return CombatEncounter.objects.filter(
        scene=scene,
        status__in=[RoundStatus.DECLARING, RoundStatus.BETWEEN_ROUNDS],
    ).first()


def encounter_requiring_risk_acknowledgement(
    scene: Scene,
    character_sheet: CharacterSheet,
) -> CombatEncounter | None:
    """Return the encounter that gates a hostile cast at this character, if any (#777).

    Non-None when ALL hold: a feedable encounter exists in the scene; its risk
    level requires acknowledgement; the character is not already actively in it
    (participant or opponent); and they have no acknowledgement on record.
    """
    encounter = _feedable_encounter(scene)
    if encounter is None:
        return None
    if encounter.risk_level not in RISK_LEVELS_REQUIRING_ACKNOWLEDGEMENT:
        return None
    if CombatParticipant.objects.filter(
        encounter=encounter,
        character_sheet=character_sheet,
        status=ParticipantStatus.ACTIVE,
    ).exists():
        return None
    if CombatOpponent.objects.filter(
        encounter=encounter,
        objectdb=character_sheet.character,
        status=OpponentStatus.ACTIVE,
    ).exists():
        return None
    if EncounterRiskAcknowledgement.objects.filter(
        encounter=encounter,
        character_sheet=character_sheet,
    ).exists():
        return None
    return encounter


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
    if encounter.status == RoundStatus.DECLARING:
        # join_encounter is the PC self-join path; valid during DECLARING.
        return join_encounter(encounter, caster_sheet)
    return add_participant(encounter, caster_sheet)


@transaction.atomic
def seed_or_feed_encounter_from_benign_intervention(
    *,
    caster_sheet: CharacterSheet,
    target_sheet: CharacterSheet,
    scene: Scene,
) -> CombatParticipant | None:
    """Seat a non-participant whose protective entrance cast landed on an embattled ally.

    The benign sibling of ``seed_or_feed_encounter_from_cast`` (#2183): no opponent row,
    no stakes lock, no FOCUSED declaration — the protective cast already resolved
    standalone; this only seats the intervener in the fight.

    Returns None when there is no feedable encounter, or the target is not
    embattled in it — a benign cast at a non-fighter is NOT combat.
    """
    encounter = _feedable_encounter(scene)
    if encounter is None:
        return None
    target_embattled = (
        CombatParticipant.objects.filter(
            encounter=encounter,
            character_sheet=target_sheet,
            status=ParticipantStatus.ACTIVE,
        ).exists()
        or CombatOpponent.objects.filter(
            encounter=encounter,
            objectdb=target_sheet.character,
            allegiance=CombatAllegiance.ALLY,
            status=OpponentStatus.ACTIVE,
        ).exists()
    )
    if not target_embattled:
        return None
    participant = _caster_participant(encounter, caster_sheet)
    acknowledge_encounter_risk(encounter, caster_sheet)
    return participant


def seat_caster_for_benign_intervention(
    *,
    caster_sheet: CharacterSheet,
    target_sheets: list[CharacterSheet],
    scene: Scene,
) -> CombatParticipant | None:
    """Seat the caster in the first encounter found among embattled targets.

    Iterates target sheets, calling ``seed_or_feed_encounter_from_benign_intervention``
    for each until one returns non-None (caster seated). Returns None when no
    target is embattled in any feedable encounter.

    Excludes the caster's own sheet from the target list — a self-cast is not
    an intervention at another PC, and ``seed_or_feed_encounter_from_benign_intervention``
    has no self-cast guard (it checks only whether the target is embattled, not
    whether the target is the caster).
    """
    for target_sheet in target_sheets:
        if target_sheet.pk == caster_sheet.pk:
            continue
        participant = seed_or_feed_encounter_from_benign_intervention(
            caster_sheet=caster_sheet,
            target_sheet=target_sheet,
            scene=scene,
        )
        if participant is not None:
            return participant
    return None


@transaction.atomic
def seed_or_feed_encounter_from_cast(  # noqa: PLR0913 - cast context + entrance marker flag
    *,
    caster_sheet: CharacterSheet,
    target_sheet: CharacterSheet,
    technique: Technique,
    scene: Scene,
    room: ObjectDB,  # noqa: OBJECTDB_PARAM
    from_entrance: bool = False,
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
        from_entrance: True when this hostile cast originated as a dramatic
            technique entrance (#2183) — stamped onto the caster's declared
            round action so a later task can fire recognition on resolution.

    Note:
        When this call CREATES a new encounter (no feedable encounter existed),
        ``CombatEncounter.opened_from_parley`` (#2536 slice 3, Task 4) is stamped True
        iff ``scene`` is itself an active, non-Battle-backed Scene at that moment (see
        ``_scene_is_active_non_battle``) — "this fight started as a conversation that
        turned hostile." Feeding an existing encounter never touches the flag. A
        CREATE also always stamps ``CombatEncounter.initiated_by_pc_side = True``
        (#2623) — this call site is always a PC's hostile cast opening the fight.
        CREATE also stamps ``CombatEncounter.on_chosen_ground`` (#2646) via
        ``world.combat.chosen_ground.compute_on_chosen_ground(room)``.

    Returns:
        The seeded or fed CombatEncounter, in DECLARING status with the caster's
        opening action declared.
    """
    encounter = _feedable_encounter(scene)
    if encounter is None:
        encounter = CombatEncounter.objects.create(
            room=room,
            scene=scene,
            status=RoundStatus.BETWEEN_ROUNDS,
            risk_level=RiskLevel.MODERATE,
            encounter_type=EncounterType.PARTY_COMBAT,
            opened_from_parley=_scene_is_active_non_battle(scene),
            initiated_by_pc_side=True,
            on_chosen_ground=compute_on_chosen_ground(room),
        )
        from world.combat.escalation import assign_default_escalation_curve  # noqa: PLC0415

        assign_default_escalation_curve(encounter)

    caster_participant = _caster_participant(encounter, caster_sheet)
    # Idempotent: the DECLARING self-join path already recorded an ack inside
    # join_encounter; this covers the add_participant and already-participating
    # branches (casting is voluntary entry).
    acknowledge_encounter_risk(encounter, caster_sheet)

    # #1770 PR4: the hostile cast is the stakes commit moment — lock any staked
    # beats on the scene for the two PCs entering combat (idempotent while an
    # activation is open, so feeding an existing encounter is safe).
    activate_stakes_for_scene(scene, [caster_sheet, target_sheet])

    existing_opponent = CombatOpponent.objects.filter(
        encounter=encounter,
        objectdb=target_sheet.character,
    ).first()
    if existing_opponent is not None and existing_opponent.status != OpponentStatus.ACTIVE:
        msg = (
            f"Cannot target {target_sheet.character.key}: already "
            f"{existing_opponent.get_status_display().lower()} in this encounter."
        )
        raise ValueError(msg)
    opponent = existing_opponent or add_opponent(
        encounter, **_opponent_kwargs_from_sheet(target_sheet)
    )

    if encounter.status == RoundStatus.BETWEEN_ROUNDS:
        begin_declaration_phase(encounter)
        encounter.refresh_from_db()

    action = declare_action(
        caster_participant,
        focused_action=technique,
        focused_category=technique.action_category,
        effort_level=EffortLevel.MEDIUM,
        focused_opponent_target=opponent,
    )
    if from_entrance and not action.from_entrance:
        action.from_entrance = True
        action.save(update_fields=["from_entrance"])

    encounter.refresh_from_db()
    return encounter
