"""ImbueAction — thread imbuing finisher (ceremony/finisher pattern).

Requires a PendingRitualEffect for 'Rite of Imbuing' (created by
PerformRitualAction when the player performs that CEREMONY-kind ritual).
On success, calls spend_resonance_for_imbuing and consumes the pending effect.
When the thread is a vow's and its shown level rose into a new focus pick level,
the result says so ("Vow level 2: 4 pts of new picks.", #4929) and carries the
opened levels in ``data["opened_pick_levels"]`` (and ``data["new_picks"]``, level and
points, which the web draws with the points in bold) for the web's "Choose picks".
A climb to a new shown level says so ("Quicksilver is now level 2."): threads are
stored x10, so the stored ``levels_gained`` is never the number a player reads.
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

        from world.covenants.focus_picks import (  # noqa: PLC0415
            new_picks,
            picks_opened_by_imbuing,
        )
        from world.magic.exceptions import (  # noqa: PLC0415
            AnchorCapExceeded,
            LevelCapExceeded,
            MagicError,
            ProtagonismLockedError,
        )
        from world.magic.models import PendingRitualEffect  # noqa: PLC0415
        from world.magic.services.resonance import spend_resonance_for_imbuing  # noqa: PLC0415
        from world.magic.services.threads import shown_thread_level  # noqa: PLC0415

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
        except MagicError as exc:
            return ActionResult(success=False, message=exc.user_message)

        opened = new_picks(picks_opened_by_imbuing(sheet, thread, result))
        lines = [row.line for row in opened]
        data = {
            "result": result,
            "opened_pick_levels": [row.level for row in opened],
            "new_picks": opened,
        }
        # Threads are stored x10 (#4585); the player reads the shown level.
        shown = shown_thread_level(result.new_level)
        rose = shown > shown_thread_level(result.new_level - result.levels_gained)
        if result.blocked_by == "CROSSING_REQUIREMENT" and result.blocked_requirement_messages:  # noqa: STRING_LITERAL
            req_list = "; ".join(result.blocked_requirement_messages)
            message = (
                f"You complete the rite, advancing {thread.name} to level "
                f"{shown}. The thread's resonance cannot cross further "
                f"until you meet the crossing requirements: {req_list}"
            )
            return ActionResult(success=True, message=_with_lines(message, lines), data=data)

        message = f"You complete the rite, imbuing {thread.name}."
        if rose:
            message += f" {thread.name} is now level {shown}."
        cap_refusal = {"LEVEL_CAP": LevelCapExceeded, "ANCHOR_CAP": AnchorCapExceeded}.get(
            result.blocked_by
        )
        if cap_refusal is not None:
            # The cap stopped the climb partway (#4585); the rest stays in the thread.
            message += f" {cap_refusal.user_message} The rest stays banked in the thread."
        return ActionResult(success=True, message=_with_lines(message, lines), data=data)


def _with_lines(message: str, lines: list[str]) -> str:
    """The rite's line, then each new-picks line on a line of its own."""
    return "\n".join([message, *lines])
