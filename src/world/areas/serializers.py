from rest_framework import serializers

from world.areas.models import Area


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
