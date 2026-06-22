"""ImbueAction — thread imbuing finisher (ceremony/finisher pattern).

Requires a PendingRitualEffect for 'Rite of Imbuing' (created by
PerformRitualAction when the player performs that CEREMONY-kind ritual).
On success, calls spend_resonance_for_imbuing and consumes the pending effect.
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
class ImbueAction(Action):
    """Advance a thread's level by spending resonance (finisher for Rite of Imbuing)."""

    key: str = "imbue_thread"
    name: str = "Imbue Thread"
    icon: str = "flame"
    category: str = "magic"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list:
        from actions.prerequisites import PendingRitualEffectPrerequisite  # noqa: PLC0415

        return [PendingRitualEffectPrerequisite("Rite of Imbuing")]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        """Validate eligibility (in the service) and advance the thread."""
        from django.db import transaction  # noqa: PLC0415

        from world.magic.exceptions import (  # noqa: PLC0415
            AnchorCapExceeded,
            InvalidImbueAmount,
            ProtagonismLockedError,
            ResonanceInsufficient,
        )
        from world.magic.models import PendingRitualEffect  # noqa: PLC0415
        from world.magic.services.resonance import spend_resonance_for_imbuing  # noqa: PLC0415

        sheet = actor.sheet_data
        thread = kwargs["thread"]
        amount = kwargs["amount"]

        try:
            with transaction.atomic():
                result = spend_resonance_for_imbuing(
                    character_sheet=sheet,
                    thread=thread,
                    amount=amount,
                )
                PendingRitualEffect.objects.filter(
                    character=sheet, ritual__name__iexact="Rite of Imbuing"
                ).delete()
        except ProtagonismLockedError as exc:
            return ActionResult(success=False, message=exc.user_message)
        except (AnchorCapExceeded, InvalidImbueAmount, ResonanceInsufficient) as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=f"You complete the rite, imbuing {thread.name}.",
            data={"result": result},
        )
