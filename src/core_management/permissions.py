"""Shared permission primitives.

The principle: staff bypass is explicitly opt-in per resource, never
automatic. Two base classes encode the policy at class definition time —
``PlayerOnlyPermission`` (staff get NO bypass) and
``PlayerOrStaffPermission`` (staff bypass everything). Subclasses override
``has_permission_for_player`` and ``has_object_permission_for_player``;
the base handles the auth/SAFE_METHODS plumbing.

For service-layer staff-aware logic, ``is_staff_observer(observer)`` is a
yes/no question. The caller decides what to do with the answer — no
automatic policy.
"""

from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, IsAuthenticated


def is_staff_observer(observer: object) -> bool:
    """Whether ``observer`` represents a staff user.

    Accepts any of: ObjectDB (character), AccountDB, Django User-like.
    For ObjectDB, walks ``character.account.is_staff``. Returns False if
    ``observer`` is None, has no ``is_staff`` attr and no associated
    account, or the associated account isn't staff.

    The helper is policy-free — it only answers the yes/no question.
    Callers that need a staff bypass call this and decide their own
    behavior.
    """
    if observer is None:
        return False
    # GETATTR_LITERAL noqa: deliberate duck-typing — observer can be any of
    # ObjectDB / AccountDB / Django User-like, and absence of the attr
    # itself is a meaningful signal handled by the default.
    is_staff = getattr(observer, "is_staff", None)  # noqa: GETATTR_LITERAL
    if is_staff is not None:
        return bool(is_staff)
    account = getattr(observer, "account", None)  # noqa: GETATTR_LITERAL
    if account is None:
        return False
    return bool(getattr(account, "is_staff", False))  # noqa: GETATTR_LITERAL


class PlayerOnlyPermission(IsAuthenticated):
    """Player-side check only. Staff get NO special bypass.

    Use for sensitive resources where staff shouldn't peek (very private
    scenes, sealed journals, secret pose targets).

    Subclasses override ``has_permission_for_player`` and
    ``has_object_permission_for_player`` to define the player-side check.
    """

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        if request.method in SAFE_METHODS:
            return True
        return self.has_permission_for_player(request, view)

    def has_object_permission(self, request, view, obj) -> bool:
        return self.has_object_permission_for_player(request, view, obj)

    def has_permission_for_player(self, request, view) -> bool:
        return True

    def has_object_permission_for_player(self, request, view, obj) -> bool:
        return True


class PlayerOrStaffPermission(PlayerOnlyPermission):
    """Like ``PlayerOnlyPermission``, but staff bypass.

    Use when staff legitimately need cross-player access — the common
    case (look at gear, edit any character's roster, manage events).
    """

    def has_permission(self, request, view) -> bool:
        if request.user.is_authenticated and request.user.is_staff:
            return True
        return super().has_permission(request, view)

    def has_object_permission(self, request, view, obj) -> bool:
        if request.user.is_staff:
            return True
        return super().has_object_permission(request, view, obj)
