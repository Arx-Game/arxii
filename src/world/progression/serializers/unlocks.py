"""Serializers for the progression unlock shop endpoint."""

from rest_framework import serializers


class ProgressionUnlockItemSerializer(serializers.Serializer):
    """Discriminated list item for purchasable progression unlocks.

    Two ``unlock_type`` variants are supported:

    - ``class_level`` — purchase a class/level unlock with XP.
    - ``thread_xp_lock`` — purchase the next XP-locked boundary on a thread.
    """

    unlock_type = serializers.CharField()
    display_name = serializers.CharField()
    xp_cost = serializers.IntegerField()
    requirements_met = serializers.BooleanField()
    locked_reason = serializers.CharField(allow_null=True)

    # Class-level fields
    class_level_unlock_id = serializers.IntegerField(allow_null=True)
    class_name = serializers.CharField(allow_null=True)
    target_level = serializers.IntegerField(allow_null=True)

    # Thread XP-lock fields
    thread_id = serializers.IntegerField(allow_null=True)
    boundary_level = serializers.IntegerField(allow_null=True)
    thread_name = serializers.CharField(allow_null=True)
    thread_level = serializers.IntegerField(allow_null=True)
    thread_resonance_id = serializers.IntegerField(allow_null=True)
    thread_resonance_name = serializers.CharField(allow_null=True)
    thread_target_kind = serializers.CharField(allow_null=True)
    dev_points_to_boundary = serializers.IntegerField(allow_null=True)


class PurchaseUnlockSerializer(serializers.Serializer):
    """Input serializer for purchasing a progression unlock."""

    UNLOCK_TYPE_CLASS_LEVEL = "class_level"
    UNLOCK_TYPE_THREAD_XP_LOCK = "thread_xp_lock"

    UNLOCK_TYPE_CHOICES = [
        (UNLOCK_TYPE_CLASS_LEVEL, "Class Level"),
        (UNLOCK_TYPE_THREAD_XP_LOCK, "Thread XP Lock"),
    ]

    unlock_type = serializers.ChoiceField(choices=UNLOCK_TYPE_CHOICES)
    class_level_unlock_id = serializers.IntegerField(
        required=False,
        allow_null=True,
    )
    thread_id = serializers.IntegerField(required=False, allow_null=True)
    boundary_level = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, data: dict) -> dict:
        """Ensure the right IDs are supplied for the chosen unlock type."""
        unlock_type = data.get("unlock_type")

        if unlock_type == self.UNLOCK_TYPE_CLASS_LEVEL:
            if data.get("class_level_unlock_id") is None:
                msg = "class_level_unlock_id is required for class_level unlocks."
                raise serializers.ValidationError(
                    {"class_level_unlock_id": msg},
                )
            return data

        if unlock_type == self.UNLOCK_TYPE_THREAD_XP_LOCK:
            if data.get("thread_id") is None or data.get("boundary_level") is None:
                msg = "thread_id and boundary_level are required for thread_xp_lock unlocks."
                raise serializers.ValidationError(
                    {"thread_id": msg, "boundary_level": msg},
                )
            return data

        msg = f"Invalid unlock_type: {unlock_type}."
        raise serializers.ValidationError({"unlock_type": msg})
