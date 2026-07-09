"""Serializers for the Motif style-binding API surface (#2030).

Request-only validators — the ``bind``/``unbind`` endpoints resolve the
``Style``/``Resonance`` objects themselves before dispatching to
``action.run()``. The ``list`` response is built directly from
``ListMotifStylesAction``'s ``ActionResult.data`` (no model serializer needed).
"""

from __future__ import annotations

from rest_framework import serializers


class MotifStyleBindSerializer(serializers.Serializer):
    style_id = serializers.IntegerField()
    resonance_id = serializers.IntegerField()


class MotifStyleUnbindSerializer(serializers.Serializer):
    style_id = serializers.IntegerField()
