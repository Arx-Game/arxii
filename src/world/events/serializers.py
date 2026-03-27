from datetime import datetime

from django.utils import timezone
from rest_framework import serializers

from world.events.models import Event, EventHost, EventInvitation, EventModification


class EventHostSerializer(serializers.ModelSerializer):
    persona_name = serializers.CharField(source="persona.name", read_only=True, default=None)

    class Meta:
        model = EventHost
        fields = ["id", "persona", "persona_name", "is_primary", "added_at"]
        read_only_fields = ["id", "persona_name", "added_at"]


class EventInvitationSerializer(serializers.ModelSerializer):
    target_name = serializers.SerializerMethodField()

    class Meta:
        model = EventInvitation
        fields = [
            "id",
            "target_type",
            "target_persona",
            "target_organization",
            "target_society",
            "target_name",
            "can_bring_guests",
            "invited_at",
        ]
        read_only_fields = ["id", "target_name", "invited_at"]

    def get_target_name(self, obj: EventInvitation) -> str | None:
        if obj.target_persona:
            return obj.target_persona.name
        if obj.target_organization:
            return obj.target_organization.name
        if obj.target_society:
            return obj.target_society.name
        return None


class EventModificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventModification
        fields = ["room_description_overlay"]


class EventListSerializer(serializers.ModelSerializer):
    primary_host_name = serializers.SerializerMethodField()
    location_name = serializers.CharField(source="location.objectdb.db_key", read_only=True)

    class Meta:
        model = Event
        fields = [
            "id",
            "name",
            "description",
            "location",
            "location_name",
            "status",
            "is_public",
            "scheduled_real_time",
            "scheduled_ic_time",
            "time_phase",
            "primary_host_name",
        ]
        read_only_fields = fields

    def get_primary_host_name(self, obj: Event) -> str | None:
        for host in obj.hosts_cached:
            if host.is_primary and host.persona:
                return host.persona.name
        return None


class EventDetailSerializer(serializers.ModelSerializer):
    hosts = EventHostSerializer(source="hosts_cached", many=True, read_only=True)
    invitations = EventInvitationSerializer(source="invitations_cached", many=True, read_only=True)
    modification = EventModificationSerializer(read_only=True, allow_null=True)
    location_name = serializers.CharField(source="location.objectdb.db_key", read_only=True)

    class Meta:
        model = Event
        fields = [
            "id",
            "name",
            "description",
            "location",
            "location_name",
            "status",
            "is_public",
            "scheduled_real_time",
            "scheduled_ic_time",
            "time_phase",
            "started_at",
            "ended_at",
            "created_at",
            "updated_at",
            "hosts",
            "invitations",
            "modification",
        ]
        read_only_fields = fields


class EventUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating events. Only mutable fields are writable."""

    class Meta:
        model = Event
        fields = [
            "name",
            "description",
            "is_public",
            "scheduled_real_time",
            "scheduled_ic_time",
            "time_phase",
        ]


class EventCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating events. Host is derived from the request."""

    class Meta:
        model = Event
        fields = [
            "name",
            "description",
            "location",
            "is_public",
            "scheduled_real_time",
            "scheduled_ic_time",
            "time_phase",
        ]

    def validate_scheduled_real_time(self, value: datetime) -> datetime:
        if value <= timezone.now():
            msg = "Scheduled time must be in the future."
            raise serializers.ValidationError(msg)
        return value
