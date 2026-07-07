"""Kinship serializers (#2062): Family + the viewer-aware tree payload.

The tree endpoint serializes ``family_tree_for``'s payload — nodes and typed
edges the requesting viewer is allowed to see (public record + truths they
know) — never raw graph rows.
"""

from rest_framework import serializers

from world.roster.models import Family, KinSlotPool, Kinsperson


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


class KinspersonNodeSerializer(serializers.Serializer):
    """One visible node in a family tree payload."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    tier = serializers.CharField()
    family_id = serializers.IntegerField(allow_null=True)
    is_deceased = serializers.BooleanField()
    is_appable = serializers.BooleanField()
    gender = serializers.CharField(allow_blank=True)
    age = serializers.IntegerField(allow_null=True)
    description = serializers.CharField(allow_blank=True)


class ParentageEdgeSerializer(serializers.Serializer):
    """One visible parentage edge in a family tree payload."""

    child_id = serializers.IntegerField()
    parent_id = serializers.IntegerField()
    kind = serializers.CharField()
    is_true = serializers.BooleanField()
    via_secret = serializers.BooleanField()


class UnionEdgeSerializer(serializers.Serializer):
    """One visible union in a family tree payload."""

    id = serializers.IntegerField()
    kind = serializers.CharField()
    member_ids = serializers.ListField(child=serializers.IntegerField())
    ended = serializers.BooleanField()


class FamilyTreeSerializer(serializers.Serializer):
    """Viewer-aware graph payload for GET /api/roster/families/{id}/tree/."""

    family = FamilySerializer()
    nodes = KinspersonNodeSerializer(many=True)
    parentage = ParentageEdgeSerializer(many=True)
    unions = UnionEdgeSerializer(many=True)


class KinSlotSerializer(serializers.ModelSerializer):
    """An open appable position (CG slot browser)."""

    allowed_genders = serializers.SlugRelatedField(many=True, read_only=True, slug_field="name")

    class Meta:
        model = Kinsperson
        fields = [
            "id",
            "name",
            "name_locked",
            "description",
            "age_min",
            "age_max",
            "allowed_genders",
            "family",
        ]
        read_only_fields = fields


class KinSlotPoolSerializer(serializers.ModelSerializer):
    """An open slot pool (CG slot browser)."""

    allowed_genders = serializers.SlugRelatedField(many=True, read_only=True, slug_field="name")
    parent_names = serializers.SerializerMethodField()

    class Meta:
        model = KinSlotPool
        fields = [
            "id",
            "family",
            "description",
            "count_remaining",
            "age_min",
            "age_max",
            "allowed_genders",
            "parent_names",
        ]
        read_only_fields = fields

    def get_parent_names(self, obj: KinSlotPool) -> list[str]:
        return [p.display_name for p in obj.parents.all()]
