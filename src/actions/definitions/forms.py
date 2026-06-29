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

# Safe message for the no-active-alt-self revert case. Mirrors the service's
# ``_NO_ACTIVE_ALT_SELF_MSG`` but kept here so the action never reaches into the
# service's private constant or — worse — leaks an exception's ``str()``.
_NO_ACTIVE_ALT_SELF_ACTION_MSG = "You have no alternate self to revert."


@dataclass
class ShiftFormAction(Action):
    """Assume an alternate self — swap in form/persona facets, assume the
    stat + ability suites. NOT gated by ``in_control``: you can assume (or be
    forced into) an alternate self while not in control (moon madness, rage).

    The ``alternate_self_id`` kwarg must be the pk of an ``AlternateSelf`` owned
    by the actor's sheet. A foreign or unknown id returns a uniform failure.
    The alt-self's optional ``persona`` FK must also belong to the actor's
    sheet — a cross-sheet persona (bad seed/admin edit) is rejected before
    reaching ``set_active_persona`` rather than raising an uncaught
    ``ActivePersonaError``.
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
        from world.forms.services import (  # noqa: PLC0415
            AlternateSelfActiveError,
            FormOwnershipError,
            assume_alternate_self,
        )
        from world.scenes.services import ActivePersonaError  # noqa: PLC0415

        sheet = actor.sheet_data
        alt = AlternateSelf.objects.filter(
            pk=kwargs.get("alternate_self_id"), character_id=sheet.pk
        ).first()
        if alt is None:
            return ActionResult(success=False, message=_UNKNOWN_ALT_SELF_MSG)
        # Defense in depth: the alt-self's ``form`` and ``persona`` FKs should
        # belong to this sheet too. ``switch_form`` raises ``FormOwnershipError``
        # and ``set_active_persona`` raises ``ActivePersonaError`` (both ValueError
        # subclasses) on a cross-sheet FK — catch them here and surface the safe
        # message instead of letting them propagate uncaught (``Action.run``
        # calls ``execute`` bare, so an uncaught exception becomes a 500 on the
        # web path).
        try:
            active = assume_alternate_self(sheet, alt)
        except AlternateSelfActiveError as exc:
            # A different alt-self is already active — revert it first.
            return ActionResult(success=False, message=exc.user_message)
        except ActivePersonaError:
            return ActionResult(success=False, message=ActivePersonaError.user_message)
        except FormOwnershipError:
            return ActionResult(success=False, message=FormOwnershipError.user_message)
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
        from world.forms.services import (  # noqa: PLC0415
            AlternateSelfActiveError,
            FormOwnershipError,
            RevertBlockedError,
            revert_alternate_self,
        )
        from world.scenes.services import ActivePersonaError  # noqa: PLC0415

        sheet = actor.sheet_data
        try:
            revert_alternate_self(sheet)
        except RevertBlockedError as exc:
            return ActionResult(success=False, message=exc.user_message)
        except ActivePersonaError:
            # The active alt-self's persona FK points at another sheet (bad
            # seed/admin edit). Surface the safe message — never ``str(exc)``.
            return ActionResult(success=False, message=ActivePersonaError.user_message)
        except FormOwnershipError:
            # The active alt-self's form FK points at another character (bad
            # seed/admin edit). Surface the safe message — never ``str(exc)``.
            return ActionResult(success=False, message=FormOwnershipError.user_message)
        except AlternateSelfActiveError as exc:
            # Revert clears the active alt-self, so this shouldn't fire from
            # the service — but if it ever does, surface the safe message.
            return ActionResult(success=False, message=exc.user_message)
        except ValueError:
            # No active alt-self to revert. Safe constant — not ``str(exc)``,
            # which would leak the exception's text (CLAUDE.md: never ``str(exc)``
            # in responses).
            return ActionResult(success=False, message=_NO_ACTIVE_ALT_SELF_ACTION_MSG)
        return ActionResult(success=True, message="You revert to your true self.")
