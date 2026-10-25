"""Getting past held ground: the pass roll (#4663, slice 2 of #4651).

A ready enemy holds the place it stands in, and a walker who enters stops there
(``held_ground``). A character whose capabilities match an approach on the challenge
``MovementConfig.held_ground_challenge`` designates may roll to get past instead. The
roll is ``resolve_challenge`` on a one-shot instance aimed at the holder, with her best
source of the approach's capability as its bonus. Three outcomes: past cleanly, past
with whatever the challenge's partial consequence authors (a strike), or stopped in the
held place.

No config row, or no challenge on it, means no pass is offered: the pass is optional
content.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.areas.positioning.exceptions import PositionError
from world.areas.positioning.services import check_move_to_position, force_move_to_position
from world.areas.positioning.traversal import traversals_of
from world.combat.constants import (
    HELD_GROUND_NO_CAPABILITY,
    HELD_GROUND_NO_CHALLENGE,
    HELD_GROUND_NOT_HELD,
    HELD_GROUND_NOT_IN_FIGHT,
    HELD_GROUND_NOT_THAT_WAY,
    CombatAllegiance,
    HeldGroundPassOutcome,
    OpponentStatus,
)
from world.combat.models import CombatOpponent, MovementConfig
from world.combat.services.held_ground import held_position_ids_against
from world.combat.services.movement_budget import active_combat_participant
from world.combat.types import PassOption, PassResult
from world.mechanics.challenge_resolution import instantiate_challenge, resolve_challenge
from world.mechanics.models import ChallengeApproach
from world.mechanics.services import get_capability_sources_for_character

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.areas.positioning.models import Position
    from world.combat.models import CombatParticipant
    from world.mechanics.models import ChallengeTemplate
    from world.mechanics.types import CapabilitySource, ChallengeResolutionResult


def pass_template() -> ChallengeTemplate | None:
    """The challenge rolled to get past held ground, or None when none is designated."""
    config = MovementConfig.objects.cached_singleton()
    if config is None:
        return None
    return config.held_ground_challenge


def pass_choices(
    actor: ObjectDB,  # noqa: OBJECTDB_PARAM - the PC mover, as held_position_ids_against
    template: ChallengeTemplate | None = None,
) -> list[PassOption]:
    """Every way ``actor`` could try to get past held ground, best first; no place read.

    Each approach on the designated challenge (``template``, read from the config when
    not handed in) whose capability the actor holds, paired with her highest-valued
    source of it, ordered by that value, highest first. Empty when no challenge is
    designated. The move list reads this once and offers it at every held neighbour.
    """
    if template is None:
        template = pass_template()
        if template is None:
            return []
    best: dict[int, CapabilitySource] = {}
    for source in get_capability_sources_for_character(actor):
        held = best.get(source.capability_id)
        if held is None or source.value > held.value:
            best[source.capability_id] = source
    if not best:
        return []
    approaches = ChallengeApproach.objects.filter(
        challenge_template=template, application__capability_id__in=best
    ).select_related("application", "check_type", "challenge_template")
    options = [
        PassOption(approach=approach, capability_source=best[approach.application.capability_id])
        for approach in approaches
    ]
    return sorted(options, key=lambda option: (-option.capability_source.value, option.approach.pk))


def pass_options(
    actor: ObjectDB,  # noqa: OBJECTDB_PARAM - the PC mover, as held_position_ids_against
    target: Position,
) -> list[PassOption]:
    """The ways ``actor`` may try to get past whoever holds ``target``, best first.

    ``pass_choices`` when ``target`` is held against her, else empty.
    """
    if target.pk not in held_position_ids_against(actor):
        return []
    return pass_choices(actor)


def _holder_in(participant: CombatParticipant, target: Position) -> CombatOpponent | None:
    """The lowest-pk ACTIVE ENEMY opponent standing in ``target`` in the participant's fight."""
    return (
        CombatOpponent.objects.filter(
            encounter=participant.encounter,
            status=OpponentStatus.ACTIVE,
            allegiance=CombatAllegiance.ENEMY,
            objectdb__object_position__position=target,
        )
        .select_related("objectdb")
        .order_by("pk")
        .first()
    )


def _choose(options: list[PassOption], approach_id: int | None) -> PassOption:
    """The option for ``approach_id``, or the best one when none is named."""
    if not options:
        raise PositionError(HELD_GROUND_NO_CAPABILITY)
    if approach_id is None:
        return options[0]
    for option in options:
        if option.approach.pk == approach_id:
            return option
    raise PositionError(HELD_GROUND_NOT_THAT_WAY)


def _outcome_of(resolution: ChallengeResolutionResult) -> HeldGroundPassOutcome:
    """Clean above success level 0, partial at 0, stopped below it.

    A resolution with no check result (an approach whose action template stopped at a
    gate or paused) never got her past: stopped.
    """
    if resolution.check_result is None:
        return HeldGroundPassOutcome.STOPPED
    level = resolution.check_result.success_level
    if level > 0:
        return HeldGroundPassOutcome.CLEAN
    if level == 0:
        return HeldGroundPassOutcome.PARTIAL
    return HeldGroundPassOutcome.STOPPED


def attempt_pass(
    actor: ObjectDB,  # noqa: OBJECTDB_PARAM - the PC mover
    target: Position,
    *,
    approach_id: int | None,
) -> PassResult:
    """Roll to get past the enemy holding ``target``, then step into it.

    Refuses, before anything changes, with ``PositionError`` naming the cause: not in a
    live fight, a step a walk could not take (``check_move_to_position`` with her
    traversals), no pass challenge designated, ``target`` not held, no capability
    matching an approach, or an ``approach_id`` that is not one of hers.

    Then, in one transaction: mints a one-shot instance of the designated challenge
    aimed at the holder, resolves it with the chosen approach (the best when
    ``approach_id`` is None), deactivates it whatever happens, and moves the actor into
    ``target`` whatever the outcome: stopped means stopped there.
    """
    participant = active_combat_participant(actor)
    if participant is None:
        raise PositionError(HELD_GROUND_NOT_IN_FIGHT)
    check_move_to_position(actor, target, traversals=traversals_of(actor))
    template = pass_template()
    if template is None:
        raise PositionError(HELD_GROUND_NO_CHALLENGE)
    holder = (
        _holder_in(participant, target) if target.pk in held_position_ids_against(actor) else None
    )
    if holder is None:
        raise PositionError(HELD_GROUND_NOT_HELD)
    option = _choose(pass_choices(actor, template), approach_id)

    with transaction.atomic():
        instance = instantiate_challenge(
            template, location=actor.location, target_object=holder.objectdb
        )
        try:
            # Every pass is rolled in the open: a hidden instance would refuse the roll.
            if not instance.is_revealed:
                instance.is_revealed = True
                instance.save(update_fields=["is_revealed"])
            resolution = resolve_challenge(
                actor, instance, option.approach, option.capability_source
            )
        finally:
            if instance.is_active:
                instance.is_active = False
                instance.save(update_fields=["is_active"])
        outcome = _outcome_of(resolution)
        force_move_to_position(actor, target)
    return PassResult(outcome=outcome, resolution=resolution, holder_name=holder.name)
