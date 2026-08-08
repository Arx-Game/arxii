"""Serializers for the web Durance readiness hub (#3045).

Mirrors telnet ``durance status`` (``commands/durance.py``) exactly — this is a
deliberately narrow, leak-scoped read: no field here exposes anything the
requesting player's own ``durance status`` output doesn't already show them.
"""

from __future__ import annotations

from rest_framework import serializers


class DuranceUnlockGateSerializer(serializers.Serializer):
    """XP-unlock + authored-requirement gate readiness for the character's next level.

    ``xp_cost`` is ``None`` only when the unlock is already purchased — an unpurchased,
    authored unlock always carries a cost, honestly reporting 0 when
    ``ClassXPCost``/``TraitXPCost`` is unauthored (the #3045 "cost unset" case is
    surfaced on the unlock-shop cards, not here; this hub only says purchased or not).
    """

    has_class_level = serializers.BooleanField()
    advancement_authored = serializers.BooleanField()
    requirements_met = serializers.BooleanField()
    failed_requirements = serializers.ListField(child=serializers.CharField())
    purchased = serializers.BooleanField()
    xp_cost = serializers.IntegerField(allow_null=True)
    class_level_unlock_id = serializers.IntegerField(allow_null=True)
    ready = serializers.BooleanField()


class DuranceEligiblePathSerializer(serializers.Serializer):
    """One eligible next-stage Path the character could semi-cross into."""

    id = serializers.IntegerField()
    name = serializers.CharField()


class DuranceIntentSerializer(serializers.Serializer):
    """The character's declared ``PathIntent``, when one exists."""

    path_id = serializers.IntegerField()
    path_name = serializers.CharField()


class DuranceStatusSerializer(serializers.Serializer):
    """Read-only Durance readiness hub — the web face of telnet ``durance status``.

    ``unlock_gate`` is ``None`` only when ``is_tier_boundary`` is True (that step
    belongs to Audere Majora, not the Durance — mirrors the telnet early-return).
    """

    level = serializers.IntegerField()
    target_level = serializers.IntegerField()
    is_tier_boundary = serializers.BooleanField()
    unlock_gate = DuranceUnlockGateSerializer(allow_null=True)
    eligible_paths = DuranceEligiblePathSerializer(many=True)
    intent = DuranceIntentSerializer(allow_null=True)
    site_present = serializers.BooleanField()


class DuranceConveneResponseSerializer(serializers.Serializer):
    """Response for a successful site-convened Durance session open."""

    session_id = serializers.IntegerField()
