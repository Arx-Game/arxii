"""Dramatic-moment suggestion confirm/dismiss actions (#2183).

Bridges the GM-facing ``GMPrompt`` inbox (Task 3's
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
    DramaticMomentSuggestionWrongKind,
    EndorsementValidationError,
)

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext
    from world.gm.models import GMPrompt
    from world.scenes.models import Scene

_MSG_WHICH_SUGGESTION = "Which suggestion? Provide a suggestion id."
_MSG_GM_ONLY = "Only the scene's GM, owner, or staff may resolve dramatic-moment suggestions."
_RESOLVE_EXCEPTIONS = (
    EndorsementValidationError,
    DramaticMomentCapExceeded,
    DramaticMomentSuggestionAlreadyResolved,
    DramaticMomentSuggestionWrongKind,
)


def _suggestion_or_none(suggestion_id: Any) -> GMPrompt | None:
    from world.gm.constants import GMPromptKind  # noqa: PLC0415
    from world.gm.models import GMPrompt  # noqa: PLC0415

    if suggestion_id is None:
        return None
    try:
        # #4101 fix round 1: GMPrompt also carries narration kinds now, each
        # addressed to one specific GM -- without this filter a scene GM/owner/
        # staff could confirm/dismiss another GM's own narration prompt by id,
        # since _account_can_gm_scene gates on the SCENE, not on addressed_to.
        return GMPrompt.objects.select_related("scene", "moment_type", "character_sheet").get(
            pk=int(suggestion_id), kind=GMPromptKind.DRAMATIC_MOMENT
        )
    except (GMPrompt.DoesNotExist, ValueError, TypeError):
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


@dataclass
class DismissGMPromptAction(_DramaticMomentSuggestionActionBase):
    """The addressed GM dismisses a narration prompt; its defaults go out (#4101).

    Expects kwargs: ``prompt_id`` (int), ``account`` (AccountDB -- must be the
    prompt's own ``addressed_to``). Unlike the dramatic-moment confirm/dismiss
    actions above (scene-GM/owner/staff gated), a narration prompt is addressed
    to one specific GM -- only that GM (or staff bypass handled inside
    ``dismiss_gm_prompt``'s caller) may close it.
    """

    key: str = "dismiss_gm_prompt"
    name: str = "Dismiss GM Prompt"
    icon: str = "x"

    def execute(self, actor, context=None, **kwargs: Any) -> ActionResult:
        from world.gm.exceptions import GMPromptError  # noqa: PLC0415
        from world.gm.models import GMPrompt  # noqa: PLC0415
        from world.gm.prompt_services import dismiss_gm_prompt  # noqa: PLC0415

        account = kwargs.get("account")
        prompt = GMPrompt.objects.filter(pk=kwargs.get("prompt_id")).first()
        if prompt is None or account is None or prompt.addressed_to_id != account.pk:
            return ActionResult(success=False, message="That prompt is not addressed to you.")
        try:
            dismiss_gm_prompt(prompt, resolver=account)
        except GMPromptError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, data={"prompt_id": prompt.pk})
