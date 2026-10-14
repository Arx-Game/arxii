"""Invoking a being's favor on a scene check (#4333, design 1).

Two scene surfaces accept a Call on favor choice:

* a scene self-check (and answering a GM's check call), which rolls at once;
* a scene action request (persuade, intimidate and the rest), which declares the
  invocation on the request (``SceneActionRequest.invoke_being``/``invoke_line``)
  and rolls it when the action's check rolls, at accept time. The roll is
  recorded once per request (``FavorInvocation.scene_action_request``), so the
  primary target, each additional target and NPC auto-resolve all add the same
  bonus without rolling again.

Room lines are the design 1 strings, written as OUTCOME interactions and
delivered live to the web and to telnet. For a secret faith the room line names
no being and omits the player's line; the acting player gets their own line in
their result.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.scenes.constants import InteractionMode
from world.scenes.interaction_services import create_interaction, deliver_outcome_interaction
from world.worship.exceptions import FavorInvocationRefused

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.checks.types import ModifierContribution
    from world.scenes.action_models import SceneActionRequest
    from world.scenes.models import Persona, Scene
    from world.worship.types import InvocationOutcome

MSG_NOT_ON_THIS_ACTION = "Calling on favor applies to an action's own check, which this has not."


def broadcast_invocation(
    outcome: InvocationOutcome,
    *,
    persona: Persona,
    scene: Scene | None,
    location: ObjectDB | None,  # noqa: OBJECTDB_PARAM - the room the lines are heard in
) -> None:
    """Write the invocation's two room lines and deliver them on commit."""
    for line in (outcome.call_line, outcome.outcome_line):
        interaction = create_interaction(
            persona=persona,
            content=line,
            mode=InteractionMode.OUTCOME,
            scene=scene,
        )
        deliver_outcome_interaction(interaction, location=location)


def declared_invocation_contribution(
    action_request: SceneActionRequest,
) -> ModifierContribution | None:
    """The FAVOR contribution for a scene action's declared invocation, if any.

    Rolls the invocation the first time it is asked for and records it against
    the request; every later call (another target, NPC auto-resolve) reads that
    record back. A refused invocation (the week's uses spent since the action was
    declared) rolls nothing and adds nothing.
    """
    from world.worship.invocation_services import (  # noqa: PLC0415
        invocation_contribution,
        invoke_favor,
    )
    from world.worship.models import FavorInvocation  # noqa: PLC0415

    if action_request.invoke_being_id is None:
        return None
    recorded = (
        FavorInvocation.objects.filter(scene_action_request=action_request)
        .select_related("being", "outcome_tier")
        .first()
    )
    if recorded is not None:
        return invocation_contribution(recorded)
    persona = action_request.initiator_persona
    sheet = persona.character_sheet
    try:
        outcome = invoke_favor(
            sheet,
            action_request.invoke_being,
            actor_name=persona.name,
            player_line=action_request.invoke_line,
            scene=action_request.scene,
            scene_action_request=action_request,
        )
    except FavorInvocationRefused:
        return None
    character = sheet.character
    broadcast_invocation(
        outcome,
        persona=persona,
        scene=action_request.scene,
        location=character.location,
    )
    if outcome.private_call_line != outcome.call_line:
        # A secret faith: the room heard "calls on something."; the player still
        # sees their own line.
        transaction.on_commit(lambda: character.msg(outcome.private_call_line))
    return outcome.contribution
