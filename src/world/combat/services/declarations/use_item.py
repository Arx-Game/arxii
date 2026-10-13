"""Declaring and resolving item use."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import ENTITY_TYPE_PC, CombatManeuver, OpponentStatus, ParticipantStatus
from world.combat.models import CombatOpponent, CombatParticipant, CombatRoundAction
from world.combat.types import ActionOutcome
from world.fatigue.constants import EffortLevel
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.items.models import ItemInstance


def declare_use_item(
    participant: CombatParticipant,
    item_instance: ItemInstance,
    *,
    target: CombatParticipant | CombatOpponent | None = None,
) -> CombatRoundAction:
    """Declare using a held on-use item as this round's action (#2023, #2120).

    Unlike FLEE/COVER (passives-only), USE_ITEM is a primary maneuver -- it is
    mutually exclusive with a declared focused technique, consuming the round's
    action slot. ``target`` may be a ``CombatParticipant`` (ally/self target) or
    a ``CombatOpponent`` (enemy target); it is resolved into
    ``focused_ally_target``/``focused_opponent_target`` respectively, reusing
    the existing FK slots rather than adding a new field. Resolution
    (``_resolve_use_item``) dispatches the existing ``UseItemAction`` machinery.
    """
    from flows.object_states.item_state import ItemState  # noqa: PLC0415
    from world.vitals.services import is_dead  # noqa: PLC0415

    encounter = participant.encounter
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot use item: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    if participant.status != ParticipantStatus.ACTIVE:
        msg = "Cannot use item: participant is no longer active in this encounter."
        raise ValueError(msg)

    if is_dead(participant.character_sheet):
        msg = "Cannot use item: character is dead."
        raise ValueError(msg)

    character = participant.character_sheet.character
    # Same wrap-without-context call HoldsItemPrerequisite uses for possession checks.
    item_state = ItemState(item_instance, context=None)  # ty: ignore[invalid-argument-type]
    if not item_state.is_in_possession(character):
        msg = "Cannot use item: you aren't holding it."
        raise ValueError(msg)

    ally_target: CombatParticipant | None = None
    opponent_target: CombatOpponent | None = None
    if isinstance(target, CombatParticipant):
        if target.encounter_id != encounter.pk or target.status != ParticipantStatus.ACTIVE:
            msg = "Use-item target must be an active participant in this encounter."
            raise ValueError(msg)
        ally_target = target
    elif isinstance(target, CombatOpponent):
        if target.encounter_id != encounter.pk or target.status != OpponentStatus.ACTIVE:
            msg = "Use-item target must be an active opponent in this encounter."
            raise ValueError(msg)
        opponent_target = target
    elif target is not None:
        msg = "Invalid use-item target type."
        raise ValueError(msg)

    action, _ = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": None,
            "focused_category": None,
            "effort_level": EffortLevel.MEDIUM,
            "focused_opponent_target": opponent_target,
            "focused_ally_target": ally_target,
            "maneuver": CombatManeuver.USE_ITEM,
            "item_instance": item_instance,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": True,
        },
    )
    return action


def _resolve_use_item(
    participant: CombatParticipant,
    action: CombatRoundAction,
) -> ActionOutcome:
    """Resolve a USE_ITEM combat maneuver by dispatching UseItemAction (#2023, #2120).

    Reuses the built UseItemAction machinery (prerequisites, effect application)
    rather than duplicating it. The item is resolved from the action's
    ``item_instance`` FK; the actor is the participant's character. Using an
    item costs the round's focused action — it is a primary maneuver, mutually
    exclusive with ``focused_action``, like FLEE/COVER/INTERPOSE.

    Two bugs fixed here (#2120): (1) the declared target was never forwarded,
    so any on-use item with a non-null ``on_use_target_kind`` (e.g. a healing
    potion used on an ally) silently self-targeted — ``focused_ally_target``/
    ``focused_opponent_target`` are now threaded through as ``target``. (2)
    ``UseItemAction`` expects an ``ObjectDB`` for its ``item`` kwarg
    (``resolve_item_instance`` walks ``target.item_instance``), but this used
    to pass the ``ItemInstance`` row itself — now resolved to its
    ``game_object`` first.
    """
    from actions.definitions.items import UseItemAction  # noqa: PLC0415

    outcome = ActionOutcome(
        entity_type=ENTITY_TYPE_PC,
        entity_label=str(participant),
    )
    outcome.participant_id = participant.pk

    if action.item_instance is not None:
        item_object = action.item_instance.game_object
        if item_object is not None:
            character = participant.character_sheet.character
            target: ObjectDB | None = None
            if action.focused_ally_target is not None:
                target = action.focused_ally_target.character_sheet.character
            elif action.focused_opponent_target is not None:
                target = action.focused_opponent_target.objectdb

            UseItemAction().run(actor=character, item=item_object, target=target)
            # UseItemAction's effects (healing, conditions) are applied by the action
            # itself; the combat round just needs to know the maneuver resolved.

    return outcome
