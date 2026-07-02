"""Per-stake resolution: machine grading, GM constrained pick, world-state writers.

#1770 PR2. stakes.py owns readiness/activation; this module owns what happens
when a staked beat completes — grading each stake to a column, firing the
authored branch's consequence pool, applying its structured world-state
writers, and writing the StakeOutcome audit/routing row.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from world.stories.constants import StakeSubjectKind
from world.stories.types import StakePayloadProblem

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.stories.models import Stake

logger = logging.getLogger(__name__)

_PILLAR_12_LIFECYCLE_MSG = (
    "sets_subject_lifecycle is only allowed for NPC_FATE stakes whose subject "
    "sheet is not player-held (pillar 12: removal is mechanically mediated — "
    "route into peril via escalates_to_risk + consequence pools instead)."
)


def sheet_is_player_held(sheet: CharacterSheet) -> bool:
    """Whether a character sheet is currently held by a player (pillar 12 gate).

    Player-held = the sheet has a RosterEntry with a current (open-ended)
    tenure. A branch payload may never write lifecycle state onto such a
    sheet — PC removal must be mechanically mediated (peril -> vitals ->
    process_damage_consequences), never GM fiat.
    """
    from world.stories.services.beats import _current_roster_entry  # noqa: PLC0415

    entry = _current_roster_entry(sheet)
    return entry is not None and entry.current_tenure is not None


def stake_resolution_payload_problems(
    *,
    stake: Stake,
    forfeits_subject_item: bool,
    npc_affection_delta: int,
    sets_subject_lifecycle: str,
) -> list[StakePayloadProblem]:
    """Validate a StakeResolution's writer payloads against its stake (pillar 12).

    Shared by StakeResolution.clean (admin defense) and
    StakeResolutionSerializer.validate (the user-input gate). Returns an empty
    list when the payload combination is legal.
    """
    problems: list[StakePayloadProblem] = []

    if sets_subject_lifecycle and (
        stake.subject_kind != StakeSubjectKind.NPC_FATE
        or stake.subject_sheet_id is None
        or sheet_is_player_held(stake.subject_sheet)
    ):
        problems.append(
            StakePayloadProblem(field="sets_subject_lifecycle", message=_PILLAR_12_LIFECYCLE_MSG)
        )

    if forfeits_subject_item and (
        stake.subject_kind != StakeSubjectKind.ITEM or stake.subject_item_id is None
    ):
        problems.append(
            StakePayloadProblem(
                field="forfeits_subject_item",
                message=("forfeits_subject_item requires an ITEM stake with subject_item set."),
            )
        )

    if npc_affection_delta != 0 and (
        stake.subject_kind not in (StakeSubjectKind.NPC_FATE, StakeSubjectKind.FACTION)
        or stake.subject_sheet_id is None
    ):
        problems.append(
            StakePayloadProblem(
                field="npc_affection_delta",
                message=(
                    "npc_affection_delta requires an NPC_FATE or FACTION stake "
                    "with subject_sheet set."
                ),
            )
        )

    return problems
