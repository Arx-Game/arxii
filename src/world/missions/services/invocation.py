"""Invoking a being's favor on a mission option's check (#4333, design 1).

The option's Attempt (solo) and a group pick accept an invocation request; the
invocation rolls first, inside ``resolve_option``, and its bonus joins the
option's ``extra_modifiers`` as support easing does. The lines go to the mission
log: every participant's narrative feed, the acting player with their own line.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

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
    """Roll ``actor``'s invocation for an option check (#4333).

    Returns None, rolling nothing, when the invocation is refused at roll time:
    a group pick's invocation is checked when picked but rolls when the node
    resolves, and the week's uses may be spent by then. The lines are posted
    once the option's own check has rolled (``deliver_invocation_to_mission_log``).
    """
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415
    from world.worship.invocation_services import invoke_favor  # noqa: PLC0415

    sheet = actor.character
    try:
        return invoke_favor(
            sheet,
            request.being,
            actor_name=active_persona_for_sheet(sheet).name,
            player_line=request.player_line,
            mission_instance=instance,
        )
    except FavorInvocationRefused:
        return None


def deliver_invocation_to_mission_log(
    instance: MissionInstance,
    actor_sheet: CharacterSheet,
    outcome: InvocationOutcome,
    check_result: CheckResult,
) -> None:
    """Post the invocation to every participant's feed, on commit (design 1 strings).

    The acting player gets their own call line, the outcome line and the check's
    breakdown with the bonus; the rest of the party gets the public call line and
    the outcome line, which for a secret faith name no being and omit the line.
    Deferred to commit so a group resolution that rolls back posts nothing.
    """
    note = f"Mission invocation (instance #{instance.pk})."
    private_body = "\n".join(
        (
            outcome.private_call_line,
            outcome.outcome_line,
            format_invocation_breakdown(beat_invocation(outcome, check_result)),
        )
    )
    public_body = f"{outcome.call_line}\n{outcome.outcome_line}"
    others = [
        participant.character
        for participant in instance.participants.select_related("character")
        if participant.character_id != actor_sheet.pk
    ]

    def _post() -> None:
        send_narrative_message(
            recipients=[actor_sheet],
            body=private_body,
            category=NarrativeCategory.STORY,
            ooc_note=note,
        )
        if others:
            send_narrative_message(
                recipients=others,
                body=public_body,
                category=NarrativeCategory.STORY,
                ooc_note=note,
            )

    transaction.on_commit(_post)


def format_invocation_breakdown(invocation: BeatInvocation) -> str:
    """The acting player's one-line check breakdown with the favor bonus.

    "Perception + Investigation: 48 + 10 Ombrin's favor (invocation: Success) = 58,
    Expert (rank 3), 32% toward Master (rank 4) against Expert (rank 3) (rank difference
    0)." Ranks carry their number and band position (#4601). Never the d100 roll.
    """
    ranks = ""
    if invocation.roller_rank and invocation.target_rank:
        without = ""
        if (
            invocation.rank_difference_without_bonus is not None
            and invocation.rank_difference_without_bonus != invocation.rank_difference
        ):
            without = f", {invocation.rank_difference_without_bonus} without the bonus"
        ranks = (
            f", {invocation.roller_rank} against {invocation.target_rank}"
            f" (rank difference {invocation.rank_difference}{without})"
        )
    bonus = f" + {invocation.bonus} {invocation.bonus_label}" if invocation.bonus else " (no bonus)"
    return (
        f"{invocation.check_type_name}: {invocation.points_before_bonus}{bonus}"
        f" = {invocation.total_points}{ranks}."
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
        roller_rank=check_result.rank_text or None,
        target_rank=check_result.target_rank_text or None,
        rank_difference=check_result.rank_difference,
        rank_difference_without_bonus=_rank_difference_without(outcome, check_result),
    )


def _rank_difference_without(outcome: InvocationOutcome, check_result: CheckResult) -> int | None:
    """The check's rank difference had the bonus not been added, or None when the
    ranks are unknown (a forced or synthesized result)."""
    from world.traits.models import CheckRank  # noqa: PLC0415

    if check_result.roller_rank is None or check_result.target_rank is None:
        return None
    rank = CheckRank.get_rank_for_points(check_result.total_points - outcome.bonus)
    if rank is None:
        return None
    return rank.rank - check_result.target_rank.rank
