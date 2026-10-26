"""Shared position serializers for use across combat, scenes, and other apps."""

from rest_framework import serializers

from world.areas.positioning.models import FeatureType


class PositionSummarySerializer(serializers.Serializer):
    """Compact public representation of a Position (id + name)."""

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)


class SquareSerializer(serializers.Serializer):
    """A battle-map square inside a place (#4651): drawing only."""

    x = serializers.IntegerField(read_only=True)
    y = serializers.IntegerField(read_only=True)


class HeldPositionSerializer(serializers.Serializer):
    """A place an enemy able to act holds, and who holds it (#4670)."""

    position_id = serializers.IntegerField(read_only=True)
    holder_names = serializers.ListField(child=serializers.CharField(), read_only=True)


class PersonaPositionSerializer(serializers.Serializer):
    """A scene persona and the Position it currently occupies (or null)."""

    persona_id = serializers.IntegerField(read_only=True)
    position = PositionSummarySerializer(read_only=True, allow_null=True)
    square_x = serializers.IntegerField(read_only=True, allow_null=True)
    square_y = serializers.IntegerField(read_only=True, allow_null=True)


class PositionAdjacencyItemSerializer(serializers.Serializer):
    """Read-only serializer for a single PositionAdjacency entry.

    Exposes the ADJACENT-reach neighbor graph for one position so the
    frontend can pre-filter selectable targets by position before declaring.
    """

    position_id = serializers.IntegerField(read_only=True)
    adjacent_position_ids = serializers.ListField(child=serializers.IntegerField(), read_only=True)


class PositionFeatureSerializer(serializers.Serializer):
    """Read-only serializer for one feature standing in a place (#4675)."""

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    art_url = serializers.CharField(read_only=True, allow_null=True)
    square_x = serializers.IntegerField(read_only=True, allow_null=True)
    square_y = serializers.IntegerField(read_only=True, allow_null=True)


class PositionNodeSerializer(serializers.Serializer):
    """Read-only serializer for one PositionNode — tactical-map node shape (#2006)."""

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    kind = serializers.CharField(read_only=True)
    elevation_anchor_id = serializers.IntegerField(read_only=True, allow_null=True)
    layout_x = serializers.IntegerField(read_only=True, allow_null=True)
    layout_y = serializers.IntegerField(read_only=True, allow_null=True)
    rampart_element = serializers.CharField(read_only=True, allow_null=True)
    rampart_integrity = serializers.IntegerField(read_only=True, allow_null=True)
    rampart_max_integrity = serializers.IntegerField(read_only=True, allow_null=True)
    rampart_crack_state = serializers.CharField(read_only=True, allow_null=True)
    is_roofed = serializers.BooleanField(read_only=True)
    screens_ranged = serializers.BooleanField(read_only=True)
    area_x = serializers.IntegerField(read_only=True, allow_null=True)
    area_y = serializers.IntegerField(read_only=True, allow_null=True)
    area_w = serializers.IntegerField(read_only=True, allow_null=True)
    area_h = serializers.IntegerField(read_only=True, allow_null=True)
    terrain_name = serializers.CharField(read_only=True, allow_null=True)
    terrain_art_url = serializers.CharField(read_only=True, allow_null=True)
    features = PositionFeatureSerializer(many=True, read_only=True)


class PositionEdgeSerializer(serializers.Serializer):
    """Read-only serializer for one PositionEdgeInfo — obstacle/gate visibility (#2006)."""

    position_a_id = serializers.IntegerField(read_only=True)
    position_b_id = serializers.IntegerField(read_only=True)
    is_passable = serializers.BooleanField(read_only=True)
    blocks_flight = serializers.BooleanField(read_only=True)
    gating_challenge_name = serializers.CharField(read_only=True, allow_null=True)
    integrity = serializers.IntegerField(read_only=True, allow_null=True)
    max_integrity = serializers.IntegerField(read_only=True, allow_null=True)


class FeatureTypeSerializer(serializers.ModelSerializer):
    """One feature type a GM can add to a place (#4675): the GM attach control's list."""

    art_url = serializers.SerializerMethodField()

    class Meta:
        model = FeatureType
        fields = ["id", "name", "reach", "art_url"]
        read_only_fields = fields

    def get_art_url(self, obj: FeatureType) -> str | None:
        return obj.art.cloudinary_url if obj.art_id else None
