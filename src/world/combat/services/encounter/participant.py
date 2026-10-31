"""Adding, removing, joining and leaving encounter participants."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.combat.constants import EncounterOutcome, EncounterType, ParticipantStatus
from world.combat.models import CombatEncounter, CombatParticipant
from world.combat.services.encounter.completion import complete_encounter
from world.combat.services.encounter.encounter_risk import acknowledge_encounter_risk
from world.combat.services.encounter.engagement import _ensure_combat_engagement
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.covenants.models import CovenantRole

ALREADY_PARTICIPATING_MESSAGE = "Already participating in this encounter."
REMOVED_BY_GM_MESSAGE = "A GM removed you from this fight."


def _create_participant(
    encounter: CombatEncounter,
    character_sheet: CharacterSheet,
    *,
    covenant_role: CovenantRole | None = None,
    status: str = ParticipantStatus.ACTIVE,
) -> CombatParticipant:
    """Seat a fighter: a CombatParticipant + its engagement, and the fighter recorded as a
    scene participant (combat participation implies SceneParticipation, #1236).

    One row per fighter per encounter. A fighter who fled or left keeps their row, so
    coming back reactivates it rather than inserting a second one (#4794); the row's
    once-per-fight ledgers (insight, vow effects fired) carry over, so leaving and
    rejoining resets nothing.
    """
    if covenant_role is None:
        from world.covenants.services import precedence_role_for_combat  # noqa: PLC0415

        covenant_role = precedence_role_for_combat(character_sheet)
    participant = CombatParticipant.objects.filter(
        encounter=encounter, character_sheet=character_sheet
    ).first()
    if participant is not None and participant.status == ParticipantStatus.ACTIVE:
        raise ValueError(ALREADY_PARTICIPATING_MESSAGE)
    if participant is None:
        participant = CombatParticipant.objects.create(
            encounter=encounter,
            character_sheet=character_sheet,
            covenant_role=covenant_role,
            status=status,
        )
    else:
        participant.covenant_role = covenant_role
        participant.status = status
        participant.save(update_fields=["covenant_role", "status"])
    _ensure_combat_engagement(participant)

    from world.combat.escalation import check_hated_foe_surges_for_new_participant  # noqa: PLC0415

    check_hated_foe_surges_for_new_participant(participant)

    if encounter.scene_id:
        from world.scenes.interaction_services import ensure_scene_participation  # noqa: PLC0415

        ensure_scene_participation(encounter.scene, character_sheet.character)
    return participant


def add_participant(
    encounter: CombatEncounter,
    character_sheet: CharacterSheet,
    *,
    covenant_role: CovenantRole | None = None,
) -> CombatParticipant:
    """Create a CombatParticipant linking a PC to an encounter.

    When no role is supplied, default to the character's combat-precedence role
    (Battle wins over Durance — Slice E).
    """
    return _create_participant(encounter, character_sheet, covenant_role=covenant_role)


def remove_participant(participant: CombatParticipant, *, by_gm: bool = False) -> None:
    """Remove a participant: status write + combat engagement teardown (#872).

    ``by_gm`` marks a GM's removal, which a self-join will not undo (#4794); a
    participant who leaves on their own may come back.
    """
    from world.mechanics.constants import EngagementType  # noqa: PLC0415
    from world.mechanics.services import end_engagement  # noqa: PLC0415

    participant.status = ParticipantStatus.REMOVED_BY_GM if by_gm else ParticipantStatus.REMOVED
    participant.save(update_fields=["status"])
    end_engagement(
        participant.character_sheet.character,
        EngagementType.COMBAT,
        source=participant.encounter,
    )


def join_encounter(
    encounter: CombatEncounter,
    character_sheet: CharacterSheet,
    *,
    covenant_role: CovenantRole | None = None,
) -> CombatParticipant:
    """Allow a PC to join an active combat encounter.

    Can join during DECLARING or BETWEEN_ROUNDS status. A fighter who fled or left
    comes back on their existing row (#4794); one a GM removed does not.
    Raises ValueError if already participating, removed by a GM, or the encounter
    is not taking joiners.
    """
    allowed = {RoundStatus.DECLARING, RoundStatus.BETWEEN_ROUNDS}
    if encounter.status not in allowed:
        msg = "Can only join during declaration or between rounds."
        raise ValueError(msg)

    # Query instead of cache — write path needs fresh data to prevent races.
    # The unique constraint is the real safety net.
    status = (
        CombatParticipant.objects.filter(encounter=encounter, character_sheet=character_sheet)
        .values_list("status", flat=True)
        .first()
    )
    if status == ParticipantStatus.ACTIVE:
        raise ValueError(ALREADY_PARTICIPATING_MESSAGE)
    if status == ParticipantStatus.REMOVED_BY_GM:
        raise ValueError(REMOVED_BY_GM_MESSAGE)

    participant = _create_participant(
        encounter, character_sheet, covenant_role=covenant_role, status=ParticipantStatus.ACTIVE
    )
    acknowledge_encounter_risk(encounter, character_sheet)
    return participant


@transaction.atomic
def leave_encounter(participant: CombatParticipant) -> None:
    """Allow a participant to voluntarily leave an Open Encounter between rounds.

    Unlike flee (a check-gated exit), this is unconditional. If the departing
    participant is the last active participant, the encounter completes as ABANDONED.

    Raises ValueError when:
    - the encounter is not in BETWEEN_ROUNDS status,
    - the encounter type is not OPEN_ENCOUNTER, or
    - the participant is not ACTIVE.
    """
    from world.combat.compulsion import reject_leave_if_compelled  # noqa: PLC0415

    reject_leave_if_compelled(participant)
    enc = CombatEncounter.objects.select_for_update().get(pk=participant.encounter_id)
    if enc.status != RoundStatus.BETWEEN_ROUNDS:
        msg = (
            f"Cannot leave: encounter status is "
            f"'{enc.get_status_display()}', expected 'Between Rounds'."
        )
        raise ValueError(msg)
    if enc.encounter_type != EncounterType.OPEN_ENCOUNTER:
        msg = (
            f"Cannot leave: encounter type is "
            f"'{enc.get_encounter_type_display()}', expected 'Open Encounter'."
        )
        raise ValueError(msg)
    # Re-read participant under the same transaction lock to avoid stale status reads.
    participant = CombatParticipant.objects.select_for_update().get(pk=participant.pk)
    if participant.status != ParticipantStatus.ACTIVE:
        msg = f"Cannot leave: participant status is '{participant.status}'."
        raise ValueError(msg)

    remove_participant(participant)

    any_active = CombatParticipant.objects.filter(
        encounter=enc,
        status=ParticipantStatus.ACTIVE,
    ).exists()
    if not any_active:
        complete_encounter(enc, outcome=EncounterOutcome.ABANDONED)
