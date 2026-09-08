"""Realm page serializers (#3725).

Read-only. The list carries what the Realms hub shows (name, formal name, first motto);
the detail adds the testament, the societies and the way in. Every hub section that
reads another app's rows goes through that app's serializers, never through these.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from world.realms.constants import TESTAMENT_THRESHOLD_LINE
from world.realms.models import Realm, RealmTestamentSection
from world.societies.models import Society


class RealmTestamentSectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RealmTestamentSection
        fields = ["sort_order", "body", "motto"]
        read_only_fields = fields


class RealmSocietySerializer(serializers.ModelSerializer):
    """A society as the realm page names it: what it says of itself and who enforces.

    Principles, reputation and the fame offset stay off the wire (hidden mechanics).
    """

    class Meta:
        model = Society
        fields = ["id", "name", "description", "enforcer_name"]
        read_only_fields = fields


class RealmStartingAreaSerializer(serializers.Serializer):
    """The way into a realm: its starting area and crest, from the accessible set."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    crest_image = serializers.CharField(allow_null=True)


class RealmListSerializer(serializers.ModelSerializer):
    """One card on the Realms hub: name, formal name, first motto, and the route key."""

    slug = serializers.CharField(read_only=True)
    first_motto = serializers.SerializerMethodField()

    class Meta:
        model = Realm
        fields = ["id", "name", "slug", "formal_name", "theme", "first_motto"]
        read_only_fields = fields

    def get_first_motto(self, obj: Realm) -> str:
        """The motto of the lowest-ordered movement, or blank when none is authored."""
        first = obj.testament_sections.order_by("sort_order").first()
        return first.motto if first is not None else ""


class RealmDetailSerializer(RealmListSerializer):
    threshold_line = serializers.SerializerMethodField()
    sections = serializers.SerializerMethodField()
    societies = RealmSocietySerializer(many=True)
    starting_area = serializers.SerializerMethodField()

    class Meta(RealmListSerializer.Meta):
        fields = [
            *RealmListSerializer.Meta.fields,
            "threshold_line",
            "sections",
            "societies",
            "starting_area",
        ]
        read_only_fields = fields

    def get_threshold_line(self, _obj: Realm) -> str:
        return TESTAMENT_THRESHOLD_LINE

    @extend_schema_field(RealmTestamentSectionSerializer(many=True))
    def get_sections(self, obj: Realm) -> list[dict]:
        """The movements in order."""
        sections = obj.testament_sections.order_by("sort_order")
        return RealmTestamentSectionSerializer(sections, many=True).data

    @extend_schema_field(RealmStartingAreaSerializer(allow_null=True))
    def get_starting_area(self, obj: Realm) -> dict | None:
        """The viewer-accessible starting area of the realm, first by name, or None.

        One area per realm today; the name order is the rule if a second is authored.
        """
        from world.character_creation.services import (  # noqa: PLC0415
            get_accessible_starting_areas,
        )

        request = self.context.get("request")
        user = request.user if request is not None else None
        if user is None:
            return None
        area = (
            get_accessible_starting_areas(user)
            .filter(realm=obj)
            .select_related("crest_art")
            .order_by("name")
            .first()
        )
        if area is None:
            return None
        crest = area.crest_art.cloudinary_url if area.crest_art_id else None
        return RealmStartingAreaSerializer(
            {"id": area.id, "name": area.name, "crest_image": crest}
        ).data
