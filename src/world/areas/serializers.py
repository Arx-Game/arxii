from rest_framework import serializers

from world.areas.models import Area


class AreaBreadcrumbSerializer(serializers.Serializer):
    """Lightweight serializer for area ancestry breadcrumbs."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    level = serializers.SerializerMethodField()

    def get_level(self, obj: Area) -> str:
        return obj.get_level_display()
