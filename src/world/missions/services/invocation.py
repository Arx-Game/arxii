"""Invoking a being's favor on a mission option's check (#4333, design 1).

The option's Attempt (solo) and a group pick accept an invocation request; the
invocation rolls first, inside ``resolve_option``, and its bonus joins the
option's ``extra_modifiers`` as support easing does. The lines go to the mission
log: every participant's narrative feed, the acting player with their own line.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.missions.constants import OptionKind
from world.missions.types import BeatInvocation
from world.narrative.constants import NarrativeCategory
from world.narrative.services import send_narrative_message
from world.worship.exceptions import FavorInvocationRefused

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.checks.types import CheckResult
    from world.missions.models import MissionInstance, MissionParticipant
    from world.missions.types import PresentedOption
    from world.worship.types import InvocationOutcome, InvocationRequest

#: Option kinds whose resolution rolls a check a bonus can land on.
ROLLED_OPTION_KINDS = frozenset({OptionKind.CHECK, OptionKind.CONTEST})


def option_rolls_check(presented: PresentedOption) -> bool:
    """True when resolving ``presented`` rolls a check (no auto-success approach)."""
    if presented.kind not in ROLLED_OPTION_KINDS:
        return False
    return not (presented.approach is not None and presented.approach.auto_succeeds)


def roll_mission_invocation(
    instance: MissionInstance, actor: MissionParticipant, request: InvocationRequest
) -> InvocationOutcome | None:
    """Roll ``actor``'s invocation for an option check and post it to the log.

    Returns None, rolling nothing, when the invocation is refused at roll time:
    a group pick's invocation is checked when picked but rolls when the node
    resolves, and the week's uses may be spent by then.
    """
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415
    from world.worship.invocation_services import invoke_favor  # noqa: PLC0415

    sheet = actor.character
    try:
        outcome = invoke_favor(
            sheet,
            request.being,
            actor_name=active_persona_for_sheet(sheet).name,
            player_line=request.player_line,
            mission_instance=instance,
        )
    except FavorInvocationRefused:
        return None
    deliver_invocation_to_mission_log(instance, sheet, outcome)
    return outcome


def deliver_invocation_to_mission_log(
    instance: MissionInstance, actor_sheet: CharacterSheet, outcome: InvocationOutcome
) -> None:
    """Post the invocation's lines to every participant's feed (design 1 strings).

    The acting player gets their own call line; the rest of the party gets the
    public one, which for a secret faith names no being and omits the line.
    """
    note = f"Mission invocation (instance #{instance.pk})."
    send_narrative_message(
        recipients=[actor_sheet],
        body=f"{outcome.private_call_line}\n{outcome.outcome_line}",
        category=NarrativeCategory.STORY,
        ooc_note=note,
    )
    others = [
        participant.character
        for participant in instance.participants.select_related("character")
        if participant.character_id != actor_sheet.pk
    ]
    if others:
        send_narrative_message(
            recipients=others,
            body=f"{outcome.call_line}\n{outcome.outcome_line}",
            category=NarrativeCategory.STORY,
            ooc_note=note,
        )


def beat_invocation(outcome: InvocationOutcome, check_result: CheckResult) -> BeatInvocation:
    """The acting player's view of an invocation and the check it changed."""
    contribution = outcome.contribution
    return BeatInvocation(
        call_line=outcome.private_call_line,
        outcome_line=outcome.outcome_line,
        bonus=outcome.bonus,
        bonus_label=contribution.source_label if contribution is not None else "",
        check_type_name=check_result.check_type.name,
        points_before_bonus=check_result.total_points - outcome.bonus,
        total_points=check_result.total_points,
        roller_rank=check_result.roller_rank.name if check_result.roller_rank else None,
        target_rank=check_result.target_rank.name if check_result.target_rank else None,
        rank_difference=check_result.rank_difference,
    )
