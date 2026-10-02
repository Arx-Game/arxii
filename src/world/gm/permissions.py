"""GM system permission classes."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from evennia.accounts.models import AccountDB
from rest_framework.permissions import BasePermission

from world.gm.constants import GMLevel, gm_level_index
from world.gm.models import GMProfile

if TYPE_CHECKING:
    from rest_framework.request import Request
    from rest_framework.views import APIView

_LIST_ACTION = "list"


class IsGM(BasePermission):
    """Require the requesting user to have a GMProfile.

    When this permission passes, views can safely access ``request.user.gm_profile``
    without try/except.
    """

    message = "You must be a GM to use this endpoint."

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not (request.user and request.user.is_authenticated):
            return False
        try:
            request.user.gm_profile  # noqa: B018  - side effect: triggers reverse lookup
        except GMProfile.DoesNotExist:
            return False
        return True


class IsGMOrStaff(BasePermission):
    """Pass if user has a GMProfile OR is staff.

    Use on endpoints that staff should access in addition to GMs (e.g. viewing
    application queues, revoking invites). Views must branch on ``is_staff``
    for staff-specific behavior where needed.
    """

    message = "You must be a GM or staff to use this endpoint."

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.is_staff:
            return True
        try:
            request.user.gm_profile  # noqa: B018
        except GMProfile.DoesNotExist:
            return False
        return True


class CanViewGMPromptQueue(BasePermission):
    """Only the scene's GM/owner/staff, or an addressed GM with a visible prompt in
    this scene's queue, may ``list`` it (#4101 fix round 3, finding M1).

    The "only the scene's GM may view an empty queue" 403 used to live inline in
    ``GMPromptViewSet.list()``, then in ``GMPromptQueueFilter.filter_queryset`` --
    this is the authorization layer the repo's ViewSet standards call for, so it
    moves here, the one place that decision is made. Scoped to the ``list`` action
    only (``view.action != "list"`` passes through unconditionally) -- ``confirm``/
    ``dismiss``/``narrate`` scope their own object lookup through
    ``prompt_visible_to`` instead, a different (per-object, not per-scene) question.
    """

    message = "Only the scene's GM may view its prompts."

    def has_permission(self, request: Request, view: APIView) -> bool:
        if view.action != _LIST_ACTION:
            return True
        from world.gm.prompt_services import (  # noqa: PLC0415
            account_can_gm_scene,
            visible_prompts_for,
        )

        scene = view.get_scene()
        account = cast(AccountDB, request.user)
        return (
            account_can_gm_scene(account, scene)
            or visible_prompts_for(account, scene=scene).exists()
        )


class HasGMTrust(BasePermission):
    """Require at least JUNIOR-tier GM trust, with a staff bypass (#2010).

    DRF counterpart to ``MinimumGMLevelPrerequisite``
    (src/actions/prerequisites.py) for read-only GM staging catalog endpoints
    (battle map blueprints, unit templates) -- STARTING GMs haven't earned
    catalog browsing yet, so the floor sits one tier above ``IsGM``/
    ``IsGMOrStaff``, which only check profile existence.
    """

    message = "You must hold at least Junior GM trust to use this endpoint."

    minimum_level = GMLevel.JUNIOR

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.is_staff:
            return True
        try:
            level = request.user.gm_profile.level
        except GMProfile.DoesNotExist:
            return False
        return gm_level_index(level) >= gm_level_index(self.minimum_level)
