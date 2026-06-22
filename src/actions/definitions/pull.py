"""PullThreadAction — thread pull (no ceremony required; always context-bound).

Pull is always in service of another declared action. The caller (CmdPull or
the web serializer) MUST supply a fully-populated PullActionContext via the
``pull_action_context`` kwarg. Never pass a bare PullActionContext() default —
_anchor_in_action returns False for TRAIT threads with empty context, causing
InvalidImbueAmount.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext


@dataclass
class PullThreadAction(Action):
    """Spend resonance through threads to activate tier effects."""

    key: str = "pull_thread"
    name: str = "Pull Thread"
    icon: str = "zap"
    category: str = "magic"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        """Validate eligibility and spend resonance through threads."""
        from world.magic.exceptions import (  # noqa: PLC0415
            MagicError,
            ProtagonismLockedError,
        )
        from world.magic.services.resonance import spend_resonance_for_pull  # noqa: PLC0415

        sheet = actor.sheet_data
        pull_ctx = kwargs["pull_action_context"]

        try:
            result = spend_resonance_for_pull(
                character_sheet=sheet,
                resonance=kwargs["resonance"],
                tier=kwargs["tier"],
                threads=kwargs["threads"],
                action_context=pull_ctx,
            )
        except ProtagonismLockedError as exc:
            return ActionResult(success=False, message=exc.user_message)
        except MagicError as exc:
            return ActionResult(success=False, message=exc.user_message)

        effects = ", ".join(e.kind for e in result.resolved_effects)
        return ActionResult(
            success=True,
            message=f"You pull resonance through your threads ({effects}).",
            data={"pull_result": result},
        )
