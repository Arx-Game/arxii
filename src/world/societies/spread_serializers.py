"""Serializers for the Spread a Tale endpoints (#745)."""

from rest_framework import serializers

from world.fatigue.constants import EffortLevel


class SpreadableDeedSerializer(serializers.Serializer):
    """A deed the persona may spread (deed picker row)."""

    id = serializers.IntegerField(read_only=True)
    title = serializers.CharField(read_only=True)
    base_value = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class SpreadInputSerializer(serializers.Serializer):
    """POST body to spread a tale: which deed, in which scene, how told."""

    scene = serializers.IntegerField()
    deed = serializers.IntegerField()
    pose_text = serializers.CharField(max_length=2000, allow_blank=True, required=False, default="")
    effort_level = serializers.ChoiceField(choices=EffortLevel.choices, default=EffortLevel.MEDIUM)
    specialization = serializers.IntegerField(
        required=False, allow_null=True, help_text="Optional Performance specialization id."
    )


class SpreadSpecializationSerializer(serializers.Serializer):
    """A Performance specialization a teller may apply (Story-weaving / Propaganda)."""

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)


class SpreadResultSerializer(serializers.Serializer):
    """Immediate ack of a spread (qualitative only — no point deltas)."""

    resolved = serializers.BooleanField(read_only=True)
    outcome = serializers.CharField(read_only=True)
    band = serializers.CharField(read_only=True)


class DeedStorySerializer(serializers.Serializer):
    """A persona's written account of a deed (#745 Phase 4 lore)."""

    id = serializers.IntegerField(read_only=True)
    author_name = serializers.CharField(source="author.name", read_only=True)
    text = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class SaveDeedStoryInputSerializer(serializers.Serializer):
    """POST body to save (or replace) the caller's account of a deed."""

    deed = serializers.IntegerField()
    text = serializers.CharField(max_length=4000)


class SceneActivitySerializer(serializers.Serializer):
    """A scene room's current activity band (shown before a teller commits)."""

    band = serializers.CharField(read_only=True)
