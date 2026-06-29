"""Thread-weaving as a real Action (telnet + web converge on action.run()).

Wraps the ``weave_thread`` service so the cross-cutting ``action.run`` machinery
(prerequisites, AP/fatigue, enhancements, events) applies uniformly — the #1331
ritual template applied to a direct-viewset mutation (#1337).
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
class WeaveThreadAction(Action):
    """Create a new Thread anchored to a target the actor is unlocked for."""

    key: str = "weave_thread"
    name: str = "Weave Thread"
    icon: str = "link"
    category: str = "magic"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list:
        from actions.prerequisites import PendingRitualEffectPrerequisite  # noqa: PLC0415

        return [PendingRitualEffectPrerequisite("Rite of Weaving")]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        """Validate eligibility (in the service) and create the thread."""
        from world.covenants.exceptions import CovenantRoleNeverHeldError  # noqa: PLC0415
        from world.magic.exceptions import (  # noqa: PLC0415
            MantleNotClearedError,
            UnsupportedGiftResonanceError,
            WeavingUnlockMissing,
        )
        from world.magic.services import weave_thread  # noqa: PLC0415

        sheet = actor.sheet_data
        try:
            thread = weave_thread(
                character_sheet=sheet,
                target_kind=kwargs["target_kind"],
                target=kwargs["target"],
                resonance=kwargs["resonance"],
                name=kwargs.get("name", ""),
                description=kwargs.get("description", ""),
            )
        except (
            WeavingUnlockMissing,
            CovenantRoleNeverHeldError,
            MantleNotClearedError,
            UnsupportedGiftResonanceError,
        ) as exc:
            return ActionResult(success=False, message=exc.user_message)

        from world.magic.models import PendingRitualEffect  # noqa: PLC0415

        PendingRitualEffect.objects.filter(
            character=sheet, ritual__name__iexact="Rite of Weaving"
        ).delete()

        return ActionResult(
            success=True,
            message=f"You weave a new thread channeling {thread.resonance}.",
            data={"thread": thread},
        )
