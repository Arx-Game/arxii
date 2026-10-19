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

    # The model's cached line lists: prefetched by the catalog ViewSet, read on
    # first access anywhere else (a test building the serializer directly).
    trait_lines = NPCPresetTraitLineSerializer(
        source="cached_trait_lines", many=True, read_only=True
    )
    skill_lines = NPCPresetSkillLineSerializer(
        source="cached_skill_lines", many=True, read_only=True
    )

    class Meta:
        model = NPCStatlinePreset
        fields = ["id", "name", "description", "trait_lines", "skill_lines"]
        read_only_fields = fields
