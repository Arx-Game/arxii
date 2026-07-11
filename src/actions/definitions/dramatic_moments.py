"""Dramatic-moment suggestion confirm/dismiss actions (#2183).

Bridges the GM-facing ``DramaticMomentSuggestion`` inbox (Task 3's
``resolve_dramatic_moment_suggestion``) to a shared web+telnet dispatch seam.

Both actions are **account-authorized** (mirroring ``actions/definitions/events.py``'s
``_HostLifecycleAction``) — a GM confirming/dismissing a suggestion from the web may
have no puppeted character at all, so they take an ``account`` kwarg and accept
``actor=None`` through ``action.run()``. The GM gate mirrors
``world.scenes.permissions.IsSceneGMOrOwnerOrStaff`` /
``SceneListSerializer.get_viewer_can_gm``: staff, or ``scene.is_gm(account)``, or
``scene.is_owner(account)`` — reusing ``Scene``'s own predicates directly since actions
have no ``request`` to hand a DRF permission class.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.prerequisites import Prerequisite
from actions.types import ActionResult, TargetType
from world.magic.exceptions import (
    DramaticMomentCapExceeded,
    DramaticMomentSuggestionAlreadyResolved,
    EndorsementValidationError,
)

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext
    from world.magic.models.dramatic_moment import DramaticMomentSuggestion
    from world.scenes.models import Scene

_MSG_WHICH_SUGGESTION = "Which suggestion? Provide a suggestion id."
_MSG_GM_ONLY = "Only the scene's GM, owner, or staff may resolve dramatic-moment suggestions."
_RESOLVE_EXCEPTIONS = (
    EndorsementValidationError,
    DramaticMomentCapExceeded,
    DramaticMomentSuggestionAlreadyResolved,
)


def _suggestion_or_none(suggestion_id: Any) -> DramaticMomentSuggestion | None:
    from world.magic.models.dramatic_moment import DramaticMomentSuggestion  # noqa: PLC0415

    if suggestion_id is None:
        return None
    try:
        return DramaticMomentSuggestion.objects.select_related(
            "scene", "moment_type", "character_sheet"
        ).get(pk=int(suggestion_id))
    except (DramaticMomentSuggestion.DoesNotExist, ValueError, TypeError):
        return None


def _account_can_gm_scene(account: AccountDB | None, scene: Scene | None) -> bool:
    """Mirror ``IsSceneGMOrOwnerOrStaff`` / ``SceneListSerializer.get_viewer_can_gm``."""
    if account is None or scene is None:
        return False
    return bool(account.is_staff or scene.is_gm(account) or scene.is_owner(account))


def _resolve_suggestion(
    *, suggestion_id: Any, account: AccountDB | None, confirm: bool
) -> ActionResult:
    """Shared confirm/dismiss body — both Actions below wrap this with their own ``confirm``."""
    from world.magic.services.gain import resolve_dramatic_moment_suggestion  # noqa: PLC0415

    suggestion = _suggestion_or_none(suggestion_id)
    if suggestion is None:
        return ActionResult(success=False, message=_MSG_WHICH_SUGGESTION)
    if not _account_can_gm_scene(account, suggestion.scene):
        return ActionResult(success=False, message=_MSG_GM_ONLY)

    try:
        resolve_dramatic_moment_suggestion(suggestion, resolver=account, confirm=confirm)
    except _RESOLVE_EXCEPTIONS as exc:
        return ActionResult(success=False, message=exc.user_message)

    verb = "confirm" if confirm else "dismiss"
    return ActionResult(
        success=True,
        message=f"You {verb} the '{suggestion.moment_type.label}' dramatic-moment suggestion.",
        data={"suggestion_id": suggestion.pk, "status": suggestion.status},
    )


@dataclass
class _DramaticMomentSuggestionActionBase(Action):
    """Shared account-authorized shape for the confirm/dismiss verbs."""

    category: str = "magic"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return []


@dataclass
class ConfirmDramaticMomentSuggestionAction(_DramaticMomentSuggestionActionBase):
    """GM confirms a PENDING suggestion, minting a real DramaticMomentTag (#2183).

    Expects kwargs: ``suggestion_id`` (int), ``account`` (AccountDB — the resolver).
    """

    key: str = "confirm_dramatic_moment_suggestion"
    name: str = "Confirm Dramatic Moment Suggestion"
    icon: str = "check"

    def execute(
        self,
        actor: ObjectDB | None,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        return _resolve_suggestion(
            suggestion_id=kwargs.get("suggestion_id"),
            account=kwargs.get("account"),
            confirm=True,
        )


@dataclass
class DismissDramaticMomentSuggestionAction(_DramaticMomentSuggestionActionBase):
    """GM dismisses a PENDING suggestion, closing it out with no tag (#2183).

    Expects kwargs: ``suggestion_id`` (int), ``account`` (AccountDB — the resolver).
    """

    key: str = "dismiss_dramatic_moment_suggestion"
    name: str = "Dismiss Dramatic Moment Suggestion"
    icon: str = "x"

    def execute(
        self,
        actor: ObjectDB | None,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        return _resolve_suggestion(
            suggestion_id=kwargs.get("suggestion_id"),
            account=kwargs.get("account"),
            confirm=False,
        )
