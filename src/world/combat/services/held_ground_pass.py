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

from world.areas.positioning.exceptions import PositionError
from world.areas.positioning.services import check_move_to_position, force_move_to_position
from world.areas.positioning.traversal import traversals_of
from world.combat.constants import CombatAllegiance, OpponentStatus
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
    from world.mechanics.models import ChallengeTemplate
    from world.mechanics.types import CapabilitySource

NO_WAY_PAST = "There is no way past them."
NOT_THAT_WAY = "You cannot get past them that way."

# PassResult.outcome values: past cleanly, past with the partial consequence, stopped.
GOT_PAST_CLEANLY = "clean"
GOT_PAST_PARTLY = "partial"
WAS_STOPPED = "stopped"


def pass_template() -> ChallengeTemplate | None:
    """The challenge rolled to get past held ground, or None when none is designated."""
    config = MovementConfig.objects.cached_singleton()
    if config is None:
        return None
    return config.held_ground_challenge


def pass_options(
    actor: ObjectDB,  # noqa: OBJECTDB_PARAM - the PC mover, as held_position_ids_against
    target: Position,
) -> list[PassOption]:
    """The ways ``actor`` may try to get past whoever holds ``target``, best first.

    Each approach on the designated challenge whose capability the actor holds, paired
    with her highest-valued source of it; ordered by that value, highest first. Empty
    when no challenge is designated or ``target`` is not held against her.
    """
    template = pass_template()
    if template is None or target.pk not in held_position_ids_against(actor):
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
    ).select_related("application", "check_type")
    options = [
        PassOption(approach=approach, capability_source=best[approach.application.capability_id])
        for approach in approaches
    ]
    return sorted(options, key=lambda option: (-option.capability_source.value, option.approach.pk))


def _holder_in(actor: ObjectDB, target: Position) -> CombatOpponent | None:  # noqa: OBJECTDB_PARAM
    """The lowest-pk ACTIVE ENEMY opponent standing in ``target`` in the actor's fight."""
    participant = active_combat_participant(actor)
    if participant is None:
        return None
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


def attempt_pass(
    actor: ObjectDB,  # noqa: OBJECTDB_PARAM - the PC mover
    target: Position,
    *,
    approach_id: int | None,
) -> PassResult:
    """Roll to get past the enemy holding ``target``, then step into it.

    Validates the step as a walk would (``check_move_to_position`` with the actor's
    traversals) before rolling. Mints a one-shot instance of the designated challenge
    aimed at the holder, resolves it with the chosen approach (``approach_id``, else the
    best option), deactivates it, and moves the actor into ``target`` whatever the
    outcome: stopped means stopped there. Raises ``PositionError`` with a player-facing
    message when there is no way past or the step is refused.
    """
    options = pass_options(actor, target)
    holder = _holder_in(actor, target) if options else None
    if holder is None:
        raise PositionError(NO_WAY_PAST)
    if approach_id is None:
        option = options[0]
    else:
        option = next((o for o in options if o.approach.pk == approach_id), None)
        if option is None:
            raise PositionError(NOT_THAT_WAY)
    check_move_to_position(actor, target, traversals=traversals_of(actor))

    instance = instantiate_challenge(
        option.approach.challenge_template,
        location=actor.location,
        target_object=holder.objectdb,
    )
    # Every pass is announced in the open: a hidden pass challenge would refuse the roll.
    if not instance.is_revealed:
        instance.is_revealed = True
        instance.save(update_fields=["is_revealed"])
    resolution = resolve_challenge(actor, instance, option.approach, option.capability_source)
    if instance.is_active:
        instance.is_active = False
        instance.save(update_fields=["is_active"])

    force_move_to_position(actor, target)
    level = resolution.check_result.success_level
    outcome = GOT_PAST_CLEANLY if level > 0 else GOT_PAST_PARTLY if level == 0 else WAS_STOPPED
    return PassResult(outcome=outcome, resolution=resolution, holder_name=holder.name)
