"""Serializers for training allocations."""

from __future__ import annotations

from typing import Any

from django.db.models import Sum
from rest_framework import serializers

from world.action_points.models import ActionPointConfig
from world.scenes.models import Persona
from world.skills.mentoring import mentor_is_waiting
from world.skills.models import TrainingAllocation
from world.skills.serializers import SkillListSerializer, SpecializationSerializer

_XOR_TARGET_MESSAGE = "Provide exactly one of skill_id or specialization_id."


class MentorPersonaSerializer(serializers.ModelSerializer):
    """Minimal read-only representation of a mentor persona."""

    class Meta:
        model = Persona
        fields = ["id", "name"]


class TrainingAllocationSerializer(serializers.ModelSerializer):
    """Read-only serializer for a character's training allocation."""

    skill = SkillListSerializer(read_only=True)
    specialization = SpecializationSerializer(read_only=True)
    mentor = MentorPersonaSerializer(read_only=True)
    remaining_weekly_budget = serializers.SerializerMethodField()
    mentor_waiting = serializers.SerializerMethodField()

    class Meta:
        model = TrainingAllocation
        fields = [
            "id",
            "skill",
            "specialization",
            "mentor",
            "mentor_accepted_at",
            "mentor_waiting",
            "ap_amount",
            "remaining_weekly_budget",
        ]
        read_only_fields = ["mentor_accepted_at"]

    def get_mentor_waiting(self, obj: TrainingAllocation) -> bool:
        """Whether a mentor was named and has not agreed, so the training counts as unmentored."""
        return mentor_is_waiting(obj)

    def get_remaining_weekly_budget(self, obj: TrainingAllocation) -> int:
        """Return AP left in the character's weekly training budget."""
        context_remaining = self.context.get("remaining_weekly_budget")
        if context_remaining is not None:
            return context_remaining
        total = (
            TrainingAllocation.objects.filter(character=obj.character).aggregate(
                total=Sum("ap_amount")
            )["total"]
            or 0
        )
        return max(0, ActionPointConfig.get_weekly_regen() - total)


class ManageTrainingAddSerializer(serializers.Serializer):
    """Validate input for creating a training allocation."""

    skill_id = serializers.IntegerField(required=False, allow_null=True)
    specialization_id = serializers.IntegerField(required=False, allow_null=True)
    ap_amount = serializers.IntegerField(min_value=1)
    mentor_persona_id = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Require exactly one of skill_id or specialization_id."""
        skill_id = attrs.get("skill_id")
        specialization_id = attrs.get("specialization_id")
        has_skill = skill_id is not None
        has_specialization = specialization_id is not None

        if has_skill and has_specialization:
            raise serializers.ValidationError(_XOR_TARGET_MESSAGE)
        if not has_skill and not has_specialization:
            raise serializers.ValidationError(_XOR_TARGET_MESSAGE)
        return attrs


class ManageTrainingUpdateSerializer(serializers.Serializer):
    """Validate input for updating a training allocation."""

    ap_amount = serializers.IntegerField(required=False, min_value=1)
    mentor_persona_id = serializers.IntegerField(required=False, allow_null=True)


class MentoringRowSerializer(serializers.Serializer):
    """One request waiting on the account's answer, or one student it teaches (#5326)."""

    allocation_id = serializers.IntegerField(read_only=True)
    student_name = serializers.CharField(read_only=True)
    # The object pronoun the request row reads: "asks Drusa Kell to teach her Villainy".
    student_pronoun = serializers.CharField(read_only=True)
    mentor_name = serializers.CharField(read_only=True)
    skill_name = serializers.CharField(read_only=True)


class MentoringListSerializer(serializers.Serializer):
    """Every request waiting on the account's answer and every student it teaches (#5326)."""

    requests = MentoringRowSerializer(many=True, read_only=True)
    students = MentoringRowSerializer(many=True, read_only=True)
