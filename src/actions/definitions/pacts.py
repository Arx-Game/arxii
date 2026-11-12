"""Being pact actions (#4341): renouncing a pact with a being."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from evennia.objects.models import ObjectDB

from actions.base import Action, ActionResult
from actions.types import ActionContext, TargetType

MSG_WHICH_BEING = "Renounce your pact with which being?"
MSG_NO_SUCH_PACT = "You hold no pact with that being."


def _resolve_being(kwargs: dict[str, Any]):
    """The being named by ``being_id`` (web) or ``being_name`` (telnet), or None."""
    from world.worship.models import WorshippedBeing  # noqa: PLC0415

    being_id = kwargs.get("being_id")
    if being_id not in (None, ""):
        try:
            return WorshippedBeing.objects.filter(pk=int(being_id)).first()
        except (TypeError, ValueError):
            return None
    name = str(kwargs.get("being_name") or "").strip()
    if not name:
        return None
    return WorshippedBeing.objects.filter(name__iexact=name).first()


@dataclass
class RenouncePactAction(Action):
    """Renounce your pact with a being (#4341).

    The pact ends (RENOUNCED), a patronage gained by the pact is released, and the
    pact's condition eases each period until it is gone.

    kwargs:
        being_id: the being's id (web).
        being_name: the being's name (telnet).
    """

    key: str = "pact_renounce"
    name: str = "Renounce Pact"
    icon: str = "scroll"
    category: str = "worship"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.pacts.exceptions import PactError  # noqa: PLC0415
        from world.pacts.services import renounce_pact  # noqa: PLC0415

        try:
            sheet = actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            sheet = None
        if sheet is None:
            return ActionResult(success=False, message="You have no character sheet.")
        if kwargs.get("being_id") in (None, "") and not str(kwargs.get("being_name") or "").strip():
            return ActionResult(success=False, message=MSG_WHICH_BEING)
        being = _resolve_being(kwargs)
        if being is None:
            return ActionResult(success=False, message=MSG_NO_SUCH_PACT)
        try:
            pact = renounce_pact(sheet, being)
        except PactError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=(
                f"You renounce your pact with {being.name}. Its cost eases each period "
                "until it is gone."
            ),
            data={"pact_id": pact.pk},
        )
