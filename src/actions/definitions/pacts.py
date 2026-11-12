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


def _resolve_being(sheet, kwargs: dict[str, Any]):
    """The being of one of her own carded pacts, named by ``being_id`` (web) or
    ``being_name`` (telnet), or None. Only her own pacts are searched, so a refusal
    never confirms that some other being exists."""
    from world.pacts.services import carded_pacts  # noqa: PLC0415

    pacts = carded_pacts().filter(character_sheet=sheet)
    being_id = kwargs.get("being_id")
    if being_id not in (None, ""):
        try:
            pacts = pacts.filter(offer__being_id=int(being_id))
        except (TypeError, ValueError):
            return None
    else:
        name = str(kwargs.get("being_name") or "").strip()
        if not name:
            return None
        pacts = pacts.filter(offer__being__name__iexact=name)
    pact = pacts.first()
    return pact.offer.being if pact is not None else None


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
        from world.pacts.exceptions import NoActivePact, PactError  # noqa: PLC0415
        from world.pacts.services import renounce_pact  # noqa: PLC0415

        try:
            sheet = actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            sheet = None
        if sheet is None:
            return ActionResult(success=False, message="You have no character sheet.")
        if kwargs.get("being_id") in (None, "") and not str(kwargs.get("being_name") or "").strip():
            return ActionResult(success=False, message=MSG_WHICH_BEING)
        being = _resolve_being(sheet, kwargs)
        if being is None:
            return ActionResult(success=False, message=MSG_NO_SUCH_PACT)
        try:
            renounced = renounce_pact(sheet, being)
        except NoActivePact:
            return ActionResult(success=False, message=MSG_NO_SUCH_PACT)
        except PactError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True, message=renounced.message, data={"pact_id": renounced.pact.pk}
        )
