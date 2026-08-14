"""Serializers for the species app's web surface (#2993)."""

from __future__ import annotations

from rest_framework import serializers


class MyLanguageSerializer(serializers.Serializer):
    """Slim shape for ``MyLanguageRow`` (``world.species.types``).

    Backs the ``my-languages`` read-only list endpoint: the requester's own
    active character's known languages, with fluency/band and which one is
    the sticky ``current_language``.
    """

    language_id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    fluency = serializers.IntegerField(read_only=True)
    band = serializers.CharField(read_only=True)
    is_current = serializers.BooleanField(read_only=True)
