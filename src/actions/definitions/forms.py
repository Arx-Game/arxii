"""Form-shift actions — the ``shift_form`` / ``revert_form`` REGISTRY actions
(#1111 slice 4). Wraps ``world.forms.services.assume_alternate_self`` /
``revert_alternate_self`` so telnet and the web share one ``action.run()`` path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext


# Uniform failure message for unknown/foreign alternate-self ids (no identity leak).
_UNKNOWN_ALT_SELF_MSG = "You have no such alternate self."


@dataclass
class ShiftFormAction(Action):
    """Assume an alternate self — swap in form/persona facets, assume the
    stat + ability suites. NOT gated by ``in_control``: you can assume (or be
    forced into) an alternate self while not in control (moon madness, rage).

    The ``alternate_self_id`` kwarg must be the pk of an ``AlternateSelf`` owned
    by the actor's sheet. A foreign or unknown id returns a uniform failure.
    """

    key: str = "shift_form"
    name: str = "Assume Form"
    icon: str = "paw-print"
    category: str = "forms"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.forms.models import AlternateSelf  # noqa: PLC0415
        from world.forms.services import assume_alternate_self  # noqa: PLC0415

        sheet = actor.sheet_data
        alt = AlternateSelf.objects.filter(
            pk=kwargs.get("alternate_self_id"), character_id=sheet.pk
        ).first()
        if alt is None:
            return ActionResult(success=False, message=_UNKNOWN_ALT_SELF_MSG)
        active = assume_alternate_self(sheet, alt)
        return ActionResult(
            success=True,
            message=f"You assume {alt.display_name or 'an alternate self'}.",
            data={"active_alternate_self_id": active.pk, "alternate_self_id": alt.pk},
        )


@dataclass
class RevertFormAction(Action):
    """Revert the active alternate self — restore return anchors, delete the
    granted stat + ability suites. ``in_control``-gated: the wrapped service
    raises ``RevertBlockedError`` while the character is not in control
    (rage/possession/charm); the action surfaces it as a failure result.
    """

    key: str = "revert_form"
    name: str = "Revert Form"
    icon: str = "arrow-uturn-left"
    category: str = "forms"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.forms.services import RevertBlockedError, revert_alternate_self  # noqa: PLC0415

        sheet = actor.sheet_data
        try:
            revert_alternate_self(sheet)
        except RevertBlockedError as exc:
            return ActionResult(success=False, message=exc.user_message)
        except ValueError as exc:
            # No active alt-self to revert.
            return ActionResult(success=False, message=str(exc))
        return ActionResult(success=True, message="You revert to your true self.")
