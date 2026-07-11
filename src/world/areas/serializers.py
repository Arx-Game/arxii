from rest_framework import serializers

from world.areas.models import Area


class WhereEntrySerializer(serializers.Serializer):
    """A `where` row: a present character + its Evennia-colour-coded room path (#1463)."""

    persona_name = serializers.CharField(read_only=True)
    room_path = serializers.CharField(read_only=True)
    room_id = serializers.IntegerField(read_only=True)


class WhoEntrySerializer(serializers.Serializer):
    """A `who` row: a present character's active-persona name + coarse idle (#1463)."""

    name = serializers.CharField(read_only=True)
    idle = serializers.CharField(read_only=True, allow_blank=True)


class AreaBreadcrumbSerializer(serializers.Serializer):
    """Lightweight serializer for area ancestry breadcrumbs."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    level = serializers.SerializerMethodField()

    def get_level(self, obj: Area) -> str:
        return obj.get_level_display()


class AreaListSerializer(serializers.ModelSerializer):
    level_display = serializers.CharField(source="get_level_display", read_only=True)
    children_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Area
        fields = ["id", "name", "level", "level_display", "children_count"]
        read_only_fields = fields


class AreaRoomSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="pk")
    name = serializers.CharField(source="objectdb.db_key")
    area_name = serializers.CharField(source="area.name", default="")
