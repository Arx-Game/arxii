"""
Family tree serializers.

Serializers for Family and FamilyMember models.
"""

from rest_framework import serializers

from world.roster.models import Family
from world.roster.models.families import FamilyMember


class FamilySerializer(serializers.ModelSerializer):
    """Serializer for family selection and display."""

    class Meta:
        model = Family
        fields = [
            "id",
            "name",
            "family_type",
            "description",
            "is_playable",
            "origin_realm",
        ]
        read_only_fields = ["id"]


class FamilyMemberSerializer(serializers.ModelSerializer):
    """Serializer for family tree members."""

    family = FamilySerializer(read_only=True)
    family_id = serializers.PrimaryKeyRelatedField(
        queryset=Family.objects.all(),
        source="family",
        write_only=True,
    )
    mother_id = serializers.PrimaryKeyRelatedField(
        queryset=FamilyMember.objects.all(),
        source="mother",
        write_only=True,
        required=False,
        allow_null=True,
    )
    father_id = serializers.PrimaryKeyRelatedField(
        queryset=FamilyMember.objects.all(),
        source="father",
        write_only=True,
        required=False,
        allow_null=True,
    )
    character_name = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()
    relationship_to_root = serializers.SerializerMethodField()

    class Meta:
        model = FamilyMember
        fields = [
            "id",
            "family",
            "family_id",
            "member_type",
            "character",
            "character_name",
            "display_name",
            "name",
            "description",
            "age",
            "mother",
            "mother_id",
            "father",
            "father_id",
            "relationship_to_root",
            "created_by",
            "created_at",
        ]
        read_only_fields = ["id", "mother", "father", "created_by", "created_at"]

    def get_character_name(self, obj: FamilyMember) -> str | None:
        """Get the character name if this is a character member."""
        if obj.character:
            return obj.character.key
        return None

    def get_display_name(self, obj: FamilyMember) -> str:
        """Get the display name for this family member."""
        return obj.get_display_name()

    def get_relationship_to_root(self, obj: FamilyMember) -> str | None:
        """Get relationship to the root member (first CHARACTER in tree)."""
        # Find root member - typically the first character member
        root = obj.family.tree_members.filter(member_type=FamilyMember.MemberType.CHARACTER).first()
        if root and root.pk != obj.pk:
            return obj.get_relationship_to(root)
        return None

    def validate(self, data):
        """Validate that mother/father are in the same family."""
        family = data.get("family")
        mother = data.get("mother")
        father = data.get("father")

        if mother and mother.family != family:
            msg = "Mother must be in the same family"
            raise serializers.ValidationError(msg)

        if father and father.family != family:
            msg = "Father must be in the same family"
            raise serializers.ValidationError(msg)

        return data


class FamilyTreeSerializer(serializers.ModelSerializer):
    """
    Serializer for complete family tree with members.

    Used for GET /api/roster/families/{id}/tree/
    """

    members = FamilyMemberSerializer(source="tree_members", many=True, read_only=True)
    open_positions_count = serializers.SerializerMethodField()

    class Meta:
        model = Family
        fields = [
            "id",
            "name",
            "family_type",
            "description",
            "origin_realm",
            "members",
            "open_positions_count",
        ]

    def get_open_positions_count(self, obj: Family) -> int:
        """Get count of open positions (placeholder members)."""
        return obj.tree_members.filter(member_type=FamilyMember.MemberType.PLACEHOLDER).count()
