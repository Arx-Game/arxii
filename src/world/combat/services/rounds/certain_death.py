"""Cancelling a pending certain-death when the actor abandons."""

from __future__ import annotations

from world.combat.constants import EncounterOutcome
from world.combat.models import CombatEncounter, CombatParticipant


def _cancel_pending_certain_death_if_abandoned(
    encounter: CombatEncounter, participants: list[CombatParticipant]
) -> None:
    """Abandoned encounters cancel any pending certain death (#4098 owner ruling).

    A GM closing a broken fight shouldn't kill anyone. The caller
    (``cleanup_completed_encounter``) MUST run this before ending Audere/Audere
    Majora: removing that condition there (via ``end_audere``/``end_audere_majora``
    -> ``remove_condition``) reaches ``_resolve_deferred_death_on_expiry``
    (``world/conditions/services.py``), which applies a pending certain death the
    instant the last deferring condition is gone — before this function's own
    caller's backstop loop (further down in ``cleanup_completed_encounter``) ever
    runs. A no-op for every other outcome (VICTORY/DEFEAT/FLED), which still apply
    the death through the ordinary seam or that backstop.
    """
    if encounter.outcome != EncounterOutcome.ABANDONED:
        return

    from world.vitals.services import clear_pending_certain_death  # noqa: PLC0415

    for participant in participants:
        clear_pending_certain_death(participant.character_sheet)
