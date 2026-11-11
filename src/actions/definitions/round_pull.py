"""A thread pull declared on its own, for the round (#5066).

A pull lasts until her next turn and boosts every use it relates to (each cast, clash,
dodge or blink is matched on its own, ``round_pull_bonus``), so she may declare one with no
cast at all. It takes no action slot: like a mark, it rides beside whatever she does this
round. The threads must relate to something she can do (``pull_alone_context``); a pull is
one per round, paid once when declared, every thread paying its tier's share.

Dispatch: REGISTRY ``registry_key="combat_pull"`` with ``pull_resonance_id``, ``pull_tier``
and ``pull_thread_ids`` (web), or a pre-built ``cast_pull`` (telnet ``combat pull``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.constants import ActionCategory
from actions.types import ActionContext, ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

NO_PULL = "Say which resonance, tier and threads to pull."
NO_BURN_ALONE = "A burn rides a cast or a clash; a pull on its own cannot burn."
PULLED = "You pull {count} thread{s} for the round."


@dataclass
class PullForTheRoundAction(Action):
    """Declare a thread pull on its own for this round (#5066)."""

    key: str = "combat_pull"
    name: str = "Pull threads"
    icon: str = "sparkles"
    category: str = "combat"
    action_category: ActionCategory = ActionCategory.MENTAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from actions.definitions.combat_maneuvers import (  # noqa: PLC0415
            NOT_IN_ACTIVE_ROUND_MESSAGE,
            _active_combat_participant,
        )
        from actions.errors import ActionDispatchError  # noqa: PLC0415
        from world.combat.pull_helpers import (  # noqa: PLC0415
            commit_combat_pull,
            pull_alone_context,
            resolve_pull_from_kwargs,
        )
        from world.magic.exceptions import MagicError  # noqa: PLC0415
        from world.scenes.constants import RoundStatus  # noqa: PLC0415

        participant = _active_combat_participant(actor, {RoundStatus.DECLARING})
        if participant is None:
            return ActionResult(success=False, message=NOT_IN_ACTIVE_ROUND_MESSAGE)
        try:
            declaration = resolve_pull_from_kwargs(participant.character_sheet, kwargs)
        except MagicError as refusal:
            return ActionResult(success=False, message=refusal.user_message)
        except ActionDispatchError as refusal:
            return ActionResult(success=False, message=refusal.user_message)
        if declaration is None:
            return ActionResult(success=False, message=NO_PULL)
        if declaration.burn > 0:
            # A burn strains the action it was declared with; a pull on its own has none.
            return ActionResult(success=False, message=NO_BURN_ALONE)
        try:
            commit_combat_pull(
                declaration,
                participant,
                participant.encounter,
                technique_id=0,
                action_context=pull_alone_context(participant),
            )
        except ActionDispatchError as refusal:
            return ActionResult(success=False, message=refusal.user_message)
        count = len(declaration.threads)
        return ActionResult(
            success=True, message=PULLED.format(count=count, s="" if count == 1 else "s")
        )
