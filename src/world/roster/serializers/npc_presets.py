"""Read serializers for the NPC statline preset catalog (#3427)."""

from __future__ import annotations

from rest_framework import serializers

from world.roster.models import NPCPresetSkillLine, NPCPresetTraitLine, NPCStatlinePreset


class NPCPresetTraitLineSerializer(serializers.ModelSerializer):
    """One STAT line, named by the trait rather than its id (#3427)."""

    trait_name = serializers.CharField(source="trait.name", read_only=True)

    class Meta:
        model = NPCPresetTraitLine
        fields = ["trait_name", "display_value"]
        read_only_fields = fields


class NPCPresetSkillLineSerializer(serializers.ModelSerializer):
    """One SKILL line, named by the skill rather than its id (#3427)."""

    skill_name = serializers.CharField(source="skill.name", read_only=True)

    class Meta:
        model = NPCPresetSkillLine
        fields = ["skill_name", "value"]
        read_only_fields = fields


class NPCStatlinePresetSerializer(serializers.ModelSerializer):
    """Read-only catalog listing for the Story-NPC mint dialog's preset picker.

    NPCStatlinePreset is authored content (a curated archetype — e.g.
    "Guard") — nothing sensitive in it, mirroring ``ThreatPoolSerializer``'s
    reasoning, but gated ``IsGMOrStaff`` (not open to any authenticated user)
    since the endpoint only has a GM-facing consumer.
    """

    # Plain nested serializers (not SerializerMethodField): the ViewSet's
    # Prefetch(to_attr="trait_lines"/"skill_lines") reuses each relation's
    # own related_name, so `instance.trait_lines`/`instance.skill_lines` is
    # a plain prefetched list on a queryset-sourced instance and the normal
    # reverse-FK manager otherwise (e.g. a unit test that builds the
    # serializer directly) — DRF's ListSerializer handles both transparently
    # (it only calls .all() when the attribute is actually a Manager), so no
    # getattr/prefetch-aware branching is needed here.
    trait_lines = NPCPresetTraitLineSerializer(many=True, read_only=True)
    skill_lines = NPCPresetSkillLineSerializer(many=True, read_only=True)

    class Meta:
        model = NPCStatlinePreset
        fields = ["id", "name", "description", "trait_lines", "skill_lines"]
        read_only_fields = fields
