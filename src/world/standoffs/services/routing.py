"""Ending a standoff by terms: an ordinary victory, with the mission routed on the terms."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.combat.models import CombatEncounter
    from world.traits.models import CheckOutcome


def settled_tier(encounter: CombatEncounter) -> CheckOutcome | None:
    """The weakest outcome among the encounter's settled groups (the terms it had to accept).

    None when no group was settled by terms (every group emptied, or no standoff), so the
    ordinary battle mapping grades the encounter instead. Missions and story beats both
    route a terms-settled standoff on this tier.
    """
    outcomes = [
        group.settled_outcome
        for group in encounter.standoff_groups.select_related("settled_outcome")
        if group.settled_outcome is not None
    ]
    if not outcomes:
        return None
    return min(outcomes, key=lambda outcome: outcome.success_level)


def complete_standoff(encounter: CombatEncounter) -> None:
    """Every group is settled: grade the mission on the terms, then complete as a VICTORY.

    ``complete_encounter`` is the one completion seam (it stamps the won-over opponents and
    emits ENCOUNTER_COMPLETED). The mission is routed first, because that stamps the deed's
    outcome and the completion handler's ``complete_encounter_for_option`` then returns
    ``None``: routed exactly once, on the terms tier rather than the battle mapping.
    """
    from world.combat.constants import EncounterOutcome  # noqa: PLC0415
    from world.combat.services import complete_encounter  # noqa: PLC0415
    from world.missions.services.encounter_option import (  # noqa: PLC0415
        complete_standoff_for_option,
    )

    if encounter.scenario_deed_id is not None:
        complete_standoff_for_option(encounter)
    complete_encounter(encounter, outcome=EncounterOutcome.VICTORY)
