"""Expiring unused pulls at the end of a round."""

from __future__ import annotations

from world.combat.models import CombatEncounter, CombatParticipant


def expire_pulls_for_round(encounter: CombatEncounter) -> None:
    """Delete all CombatPull rows from prior rounds and recompute affected max_health.

    Spec A §3.8 lines 1057–1078 + §7.4 lines 2031–2039. Called from
    ``begin_declaration_phase`` immediately after ``round_number`` advances.

    - Collects distinct ``participant_id``s whose pulls are about to expire.
    - Cascade-deletes the stale ``CombatPull`` rows (the FK cascade drops
      their ``CombatPullResolvedEffect`` children).
    - Invalidates each affected participant's ``CharacterCombatPullHandler``
      cache so the next read of ``combat_pulls.active_pull_vital_bonuses``
      reflects the deletion.
    - Calls ``recompute_max_health_with_threads`` per participant so any
      expiring MAX_HEALTH pull goes away via the clamp-not-injure path in
      ``vitals.recompute_max_health`` — characters are never *injured* by
      a pull expiring, only un-bolstered.

    Side-effect-free for participants with no active pulls this encounter.
    """
    from world.combat.models import CombatPull  # noqa: PLC0415
    from world.magic.services import (  # noqa: PLC0415
        recompute_max_health_with_threads,
    )

    stale_pulls = CombatPull.objects.filter(
        encounter=encounter,
        round_number__lt=encounter.round_number,
    )
    affected_participant_ids = list(stale_pulls.values_list("participant_id", flat=True).distinct())
    if not affected_participant_ids:
        return

    stale_pulls.delete()

    # Re-fetch participants so we can walk to character_sheet.character —
    # SharedMemoryModel returns the identity-mapped instances, so this is
    # zero-query once the participants have been loaded in the request.
    participants = CombatParticipant.objects.filter(
        pk__in=affected_participant_ids,
    ).select_related("character_sheet__character")
    for p in participants:
        p.character_sheet.character.combat_pulls.invalidate()
        recompute_max_health_with_threads(p.character_sheet)
