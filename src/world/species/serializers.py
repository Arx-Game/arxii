"""Serializers for the species app's web surface (#2993)."""

from __future__ import annotations

from rest_framework import serializers


class MyLanguageSerializer(serializers.Serializer):
    """Slim shape for ``MyLanguageRow`` (``world.species.types``).

    Backs the ``my-languages`` read-only list endpoint: the requester's own
    active character's known languages. ``fluency``/``band`` are TRAINED (the
    picker lists ``fluency > 0`` rows only); ``effective_fluency``/``effective_band``
    add active-condition bonuses (#4090), and ``temporary_sources`` names the
    conditions contributing to that bonus (empty when none). ``is_current`` is
    which language is the sticky ``current_language``.
    """

    language_id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    fluency = serializers.IntegerField(read_only=True)
    band = serializers.CharField(read_only=True)
    is_current = serializers.BooleanField(read_only=True)
    effective_fluency = serializers.IntegerField(read_only=True)
    effective_band = serializers.CharField(read_only=True)
    temporary_sources = serializers.ListField(child=serializers.CharField(), read_only=True)
