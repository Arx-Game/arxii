"""Serializers for the Signature bonus API surface (#1728 Task 4).

Request-only validators — the ``set``/``clear`` endpoints resolve the
``Thread``/``SignatureMotifBonus`` objects themselves before dispatching to
``action.run()``. The ``list`` response is built directly from
``SignatureListAction``'s ``ActionResult.data`` (no model serializer needed).
"""

from __future__ import annotations

from rest_framework import serializers


class SignatureSetSerializer(serializers.Serializer):
    thread_id = serializers.IntegerField()
    bonus_id = serializers.IntegerField()


class SignatureClearSerializer(serializers.Serializer):
    thread_id = serializers.IntegerField()
