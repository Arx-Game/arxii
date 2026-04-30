"""DRF serializers for covenants API."""

from rest_framework import serializers

from world.covenants.models import CharacterCovenantRole, CovenantRole, GearArchetypeCompatibility


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

    class Meta:
        model = CharacterCovenantRole
        fields = ["id", "character_sheet", "covenant_role", "joined_at", "left_at", "is_active"]
        read_only_fields = fields

    def get_is_active(self, obj: CharacterCovenantRole) -> bool:
        return obj.left_at is None


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
