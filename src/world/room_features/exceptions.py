"""Typed exceptions for the room_features app.

Per CLAUDE.md `ViewSet & API Design`: typed exceptions with `user_message`
property. View and Action layers read `exc.user_message`, never `str(exc)`.
"""


class RoomFeatureError(Exception):
    """Base for room_features typed exceptions."""

    user_message: str = "A room-feature error occurred."


class RoomAlreadyHasFeatureError(RoomFeatureError):
    """Raised when installing a feature into a room that already has one (any kind).

    RoomFeatureInstance.room_profile is a OneToOneField(primary_key=True) — a room
    hosts at most one feature instance of any kind. Generalizes the guard clause
    world/magic/services/sanctum_install.py already uses for the ritual install path,
    so the generic project-based install path (#1234) can raise it too.
    """

    user_message = "This room already has a feature installed."
