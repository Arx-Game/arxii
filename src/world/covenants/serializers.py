"""DRF serializers for covenants API."""

from rest_framework import serializers

from world.covenants.handlers import can_engage_durance_membership
from world.covenants.models import (
    CharacterCovenantRole,
    Covenant,
    CovenantLevelThreshold,
    CovenantRite,
    CovenantRole,
    GearArchetypeCompatibility,
)


class CovenantRoleSerializer(serializers.ModelSerializer):
    """Read-only serializer for CovenantRole lookup data."""

    covenant_type_display = serializers.CharField(
        source="get_covenant_type_display", read_only=True
    )
    archetype_display = serializers.CharField(source="get_archetype_display", read_only=True)

    class Meta:
        model = CovenantRole
        fields = [
            "id",
            "name",
            "slug",
            "covenant_type",
            "covenant_type_display",
            "archetype",
            "archetype_display",
            "speed_rank",
            "description",
        ]
        read_only_fields = fields


class CharacterCovenantRoleSerializer(serializers.ModelSerializer):
    """Read-only serializer for a character's covenant role assignment."""

    covenant_role = CovenantRoleSerializer(read_only=True)
    is_active = serializers.SerializerMethodField()
    can_engage = serializers.SerializerMethodField()
    engage_blocked_reason = serializers.SerializerMethodField()

    class Meta:
        model = CharacterCovenantRole
        fields = [
            "id",
            "character_sheet",
            "covenant",
            "covenant_role",
            "engaged",
            "joined_at",
            "left_at",
            "is_active",
            "can_engage",
            "engage_blocked_reason",
        ]
        read_only_fields = fields

    def get_is_active(self, obj: CharacterCovenantRole) -> bool:
        return obj.left_at is None

    def get_can_engage(self, obj: CharacterCovenantRole) -> bool:
        return can_engage_durance_membership(obj)

    def get_engage_blocked_reason(self, obj: CharacterCovenantRole) -> str | None:
        if can_engage_durance_membership(obj):
            return None
        return "No covenant members present in this scene."


class CovenantSerializer(serializers.ModelSerializer):
    """Read-only serializer for Covenant identity, type, level, and lifecycle state."""

    covenant_type_display = serializers.CharField(
        source="get_covenant_type_display", read_only=True
    )
    member_count = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()
    legend_total = serializers.SerializerMethodField()
    storylines = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = Covenant
        fields = [
            "id",
            "name",
            "covenant_type",
            "covenant_type_display",
            "level",
            "sworn_objective",
            "formed_at",
            "dissolved_at",
            "is_active",
            "member_count",
            "legend_total",
            "storylines",
        ]
        read_only_fields = fields

    def get_member_count(self, obj: Covenant) -> int:
        return obj.memberships.filter(left_at__isnull=True).count()

    def get_is_active(self, obj: Covenant) -> bool:
        return obj.dissolved_at is None

    def get_legend_total(self, obj: Covenant) -> int:
        from world.societies.services import get_covenant_legend_total  # noqa: PLC0415

        return get_covenant_legend_total(obj)


class PromoteSubroleSerializer(serializers.Serializer):
    """Input serializer for the CharacterCovenantRoleViewSet.promote action.

    Validates that the target sub-role's parent matches the membership's current role.
    The actual promotion is performed by the promote_to_subrole service function.
    """

    target_subrole = serializers.PrimaryKeyRelatedField(
        queryset=CovenantRole.objects.filter(parent_role__isnull=False),
    )

    def validate_target_subrole(self, subrole: CovenantRole) -> CovenantRole:
        membership: CharacterCovenantRole = self.context["membership"]
        if subrole.parent_role_id != membership.covenant_role_id:
            msg = "Target sub-role's parent must match your current role in this covenant."
            raise serializers.ValidationError(msg)
        return subrole


class CovenantLevelThresholdSerializer(serializers.ModelSerializer):
    """Read-only serializer for CovenantLevelThreshold lookup rows."""

    class Meta:
        model = CovenantLevelThreshold
        fields = ("level", "required_legend")


class CovenantRiteSerializer(serializers.ModelSerializer):
    """Read-only serializer for CovenantRite authored definitions."""

    covenant_type_display = serializers.CharField(
        source="get_covenant_type_display", read_only=True
    )

    class Meta:
        model = CovenantRite
        fields = [
            "id",
            "ritual",
            "covenant_type",
            "covenant_type_display",
            "min_covenant_level",
            "min_engaged_present",
            "granted_condition",
            "base_severity",
            "severity_per_extra_participant",
            "max_severity",
            "duration_rounds",
        ]
        read_only_fields = fields


class GearArchetypeCompatibilitySerializer(serializers.ModelSerializer):
    """Read-only serializer for GearArchetypeCompatibility join rows."""

    gear_archetype_display = serializers.CharField(
        source="get_gear_archetype_display", read_only=True
    )

    class Meta:
        model = GearArchetypeCompatibility
        fields = [
            "id",
            "covenant_role",
            "gear_archetype",
            "gear_archetype_display",
        ]
        read_only_fields = fields
