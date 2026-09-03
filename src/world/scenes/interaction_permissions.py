from __future__ import annotations

from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView

from world.roster.models import RosterEntry
from world.scenes.constants import InteractionMode, InteractionVisibility, ScenePrivacyMode
from world.scenes.models import Interaction
from world.scenes.place_models import InteractionReceiver


def get_account_roster_entries(request: Request) -> list[RosterEntry]:
    """Roster entries the authenticated account holds a current tenure on.

    A stateless read of ``Account.cached_roster_entries`` (ADR-0260, #3597); the
    only work here is the anonymous guard. Nothing is stored on the request.
    """
    user = request.user
    if not user.is_authenticated:
        return []
    return user.cached_roster_entries


def get_account_personas(request: Request) -> list[int]:
    """Every persona id (any type) on a sheet the authenticated account plays."""
    user = request.user
    if not user.is_authenticated:
        return []
    return user.cached_persona_ids


def _is_receiver_or_writer(
    obj: Interaction,
    persona_ids: list[int],
) -> bool:
    """Check if any of the persona IDs match the interaction's writer or receivers."""
    if not persona_ids:
        return False
    is_writer = obj.persona_id in persona_ids
    is_receiver = InteractionReceiver.objects.filter(
        interaction=obj,
        persona_id__in=persona_ids,
    ).exists()
    return is_writer or is_receiver


def _requires_receiver_check(obj: Interaction) -> bool:
    """Return True if the interaction is restricted to receivers/writer only."""
    if obj.visibility == InteractionVisibility.VERY_PRIVATE:
        return True
    if obj.visibility == InteractionVisibility.PERCEIVED_ONLY:
        # #2710 — only the characters who perceived the event. Staff still pass,
        # via the is_staff branch above the caller's use of this predicate.
        return True
    if obj.place_id is not None:
        return True
    scene = obj.scene
    if scene and scene.privacy_mode == ScenePrivacyMode.PRIVATE:
        return True
    if obj.mode == InteractionMode.WHISPER:
        return True
    return False


class CanViewInteraction(permissions.BasePermission):
    """Permission to check if user can view a specific interaction."""

    def has_object_permission(self, request: Request, view: APIView, obj: Interaction) -> bool:
        user = request.user
        persona_ids = get_account_personas(request)

        # Very private: only receivers/writer personas, never staff
        if obj.visibility == InteractionVisibility.VERY_PRIVATE:
            return _is_receiver_or_writer(obj, persona_ids)

        # Staff sees everything except very_private
        if user.is_staff:
            return True

        # Directed or escalated-visibility content (whisper, place-scoped table talk,
        # PERCEIVED_ONLY, or a private scene) is NOT made public by its scene being
        # public -- this must run BEFORE the public-scene branch below, or a
        # receiver-scoped interaction sitting inside a public scene leaks to everyone.
        # (#2710 review: the public-scene branch previously ran first and always won,
        # so this predicate's whisper/place/PERCEIVED_ONLY restrictions were dead code
        # for any interaction in a public scene -- the common case. Mirrors the order
        # already correct in the sibling service function, can_view_interaction.)
        if _requires_receiver_check(obj):
            return _is_receiver_or_writer(obj, persona_ids)

        # Public scene: visible to all
        scene = obj.scene
        if scene and scene.privacy_mode == ScenePrivacyMode.PUBLIC:
            return True

        # Default: public (pose/emit/say/shout/action without a scene)
        return True


class IsInteractionWriter(permissions.BasePermission):
    """Only the writer can modify/delete their interaction."""

    def has_object_permission(self, request: Request, view: APIView, obj: Interaction) -> bool:
        persona_ids = get_account_personas(request)
        return obj.persona_id in persona_ids
