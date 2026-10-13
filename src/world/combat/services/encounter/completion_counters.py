"""Incrementing per-encounter completion counters."""

from __future__ import annotations

from world.combat.constants import EncounterOutcome, EncounterType, ParticipantStatus
from world.combat.models import CombatEncounter, CombatParticipant


def _increment_completion_counters(encounter: CombatEncounter, outcome: EncounterOutcome) -> None:
    """encounters_won / encounters_lost / encounters_fled aggregates (#876 §7).

    A DUEL leaves both PCs as ACTIVE participants at completion (only the loser's
    mirror ``CombatOpponent`` is DEFEATED, never the loser's own participant row),
    so the generic ACTIVE→won rule would credit *both* duelists with a win. For a
    DUEL the win is credited solely to ``encounter.duel_winner`` and the loss to
    the other duelist; an abandoned duel (no ``duel_winner``) credits neither
    (#1182).

    Buckets participants by outcome and makes ONE group counter call per bucket
    (#3075) — everyone who fled, everyone who won, everyone who lost is a
    genuinely simultaneous moment, so a first-ever threshold achievement shares
    its Discovery across the whole bucket instead of going solely to whichever
    participant a per-sheet loop happened to process first. Buckets never share
    a stat, so no cross-bucket moment exists.
    """
    from world.combat.achievement_counters import (  # noqa: PLC0415
        STAT_KEY_ENCOUNTERS_FLED,
        STAT_KEY_ENCOUNTERS_LOST,
        STAT_KEY_ENCOUNTERS_WON,
        increment_combat_counter_for_group,
    )

    # Ordered by join order (#3319). Nothing player-facing rides on this: the bucket
    # lists go to ``increment_stat_for_group`` -> ``grant_achievement``, which puts the
    # first sheet in the primary ``Discovery.discovered_by_tenure`` FK and the rest in
    # ``shared_with_tenures``, and #3063 ruled that split invisible -- every member of a
    # group discovery reads identically as "shared". Unordered, though, the split fell
    # out of Postgres heap order, which shifts whenever ``_apply_aftermath_rules``
    # rewrites a participant row, and made the arbitrary choice unreproducible run to
    # run. Ordering by pk keeps it stable without making it mean anything.
    participants = (
        CombatParticipant.objects.filter(encounter=encounter)
        .select_related("character_sheet")
        .order_by("pk")
    )

    if encounter.encounter_type == EncounterType.DUEL:
        winner_sheet_id = encounter.duel_winner_id
        fled_sheets = []
        winner_sheets = []
        loser_sheets = []
        for participant in participants:
            if participant.status == ParticipantStatus.FLED:
                fled_sheets.append(participant.character_sheet)
            elif winner_sheet_id is None:
                continue  # Abandoned / mutual stop — no victor; credit neither.
            elif participant.character_sheet_id == winner_sheet_id:
                winner_sheets.append(participant.character_sheet)
            else:
                loser_sheets.append(participant.character_sheet)
        increment_combat_counter_for_group(fled_sheets, STAT_KEY_ENCOUNTERS_FLED)
        increment_combat_counter_for_group(winner_sheets, STAT_KEY_ENCOUNTERS_WON)
        increment_combat_counter_for_group(loser_sheets, STAT_KEY_ENCOUNTERS_LOST)
        return

    outcome_key = {
        EncounterOutcome.VICTORY: STAT_KEY_ENCOUNTERS_WON,
        EncounterOutcome.DEFEAT: STAT_KEY_ENCOUNTERS_LOST,
    }.get(outcome)

    fled_sheets = []
    outcome_sheets = []
    for participant in participants:
        if participant.status == ParticipantStatus.FLED:
            fled_sheets.append(participant.character_sheet)
        elif participant.status == ParticipantStatus.ACTIVE and outcome_key is not None:
            outcome_sheets.append(participant.character_sheet)
    increment_combat_counter_for_group(fled_sheets, STAT_KEY_ENCOUNTERS_FLED)
    if outcome_key is not None:
        increment_combat_counter_for_group(outcome_sheets, outcome_key)
