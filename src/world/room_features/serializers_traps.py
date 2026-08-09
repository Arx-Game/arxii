"""Serializers for the player-facing trap read surface (#3011).

Deliberately narrow — see the leak table in the issue spec: no consequence
pool, no difficulties, no check types. A player only ever needs a trap's
identity (to disarm it) and whether it's currently armed.
"""

from __future__ import annotations

from rest_framework import serializers

from world.room_features.models import Trap


class TrapSerializer(serializers.ModelSerializer):
    """One trap visible to the requesting character (#3011).

    Visibility is entirely the caller's job (``RoomTrapViewSet.list`` —
    armed, plus ``is_hidden=False`` or already in the viewer's own
    ``detected_by``) — this serializer trusts the queryset and exposes only
    the fields a player is allowed to know about a trap they can see:
    identity (for the disarm dispatch's ``trap_id``) and armed state.
    ``Trap`` carries no ``description`` field (unlike the leak table's
    aspirational field list) — only ``name`` identifies it to a player today;
    adding authored flavor text is a separate content-model change, out of
    scope here.
    """

    class Meta:
        model = Trap
        fields = ["id", "name", "is_armed"]
        read_only_fields = fields


class RoomTrapRequestSerializer(serializers.Serializer):
    """Query-param validation for the trap read — a required character id.

    Mirrors ``PortalDestinationsRequestSerializer``/``ComfortRequestSerializer``:
    ``character_id`` is the character's ObjectDB pk (== ``CharacterSheet`` pk by
    construction).
    """

    character_id = serializers.IntegerField()
