"""
Family tree serializers.

Serializers for Family, FamilyMember, and FamilyRelationship models.
"""

from rest_framework import serializers

from world.roster.models import Family
from world.roster.models.families import FamilyMember, FamilyRelationship


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
    character_name = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()

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
            "created_by",
            "created_at",
        ]
        read_only_fields = ["id", "created_by", "created_at"]

    def get_character_name(self, obj: FamilyMember) -> str | None:
        """Get the character name if this is a character member."""
        if obj.character:
            return obj.character.key
        return None

    def get_display_name(self, obj: FamilyMember) -> str:
        """Get the display name for this family member."""
        return obj.get_display_name()


class FamilyRelationshipSerializer(serializers.ModelSerializer):
    """Serializer for family relationships."""

    from_member = FamilyMemberSerializer(read_only=True)
    from_member_id = serializers.PrimaryKeyRelatedField(
        queryset=FamilyMember.objects.all(),
        source="from_member",
        write_only=True,
    )
    to_member = FamilyMemberSerializer(read_only=True)
    to_member_id = serializers.PrimaryKeyRelatedField(
        queryset=FamilyMember.objects.all(),
        source="to_member",
        write_only=True,
    )

    class Meta:
        model = FamilyRelationship
        fields = [
            "id",
            "from_member",
            "from_member_id",
            "to_member",
            "to_member_id",
            "relationship_type",
            "notes",
        ]
        read_only_fields = ["id"]

    def validate(self, data):
        """Validate that from_member and to_member are in the same family."""
        from_member = data.get("from_member")
        to_member = data.get("to_member")

        if from_member and to_member:
            if from_member.family != to_member.family:
                msg = "Both members must be in the same family"
                raise serializers.ValidationError(msg)

            if from_member == to_member:
                msg = "A member cannot have a relationship with themselves"
                raise serializers.ValidationError(msg)

        return data


class FamilyTreeSerializer(serializers.ModelSerializer):
    """
    Serializer for complete family tree with members and relationships.

    Used for GET /api/roster/families/{id}/tree/
    """

    members = FamilyMemberSerializer(source="tree_members", many=True, read_only=True)
    relationships = serializers.SerializerMethodField()
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
            "relationships",
            "open_positions_count",
        ]

    def get_relationships(self, obj: Family) -> list[dict]:
        """Get all relationships for members of this family."""
        relationships = FamilyRelationship.objects.filter(from_member__family=obj).select_related(
            "from_member", "to_member"
        )
        return FamilyRelationshipSerializer(relationships, many=True).data

    def get_open_positions_count(self, obj: Family) -> int:
        """Get count of open positions (placeholder members)."""
        return obj.tree_members.filter(member_type=FamilyMember.MemberType.PLACEHOLDER).count()
