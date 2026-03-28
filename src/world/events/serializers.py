from datetime import datetime

from django.utils import timezone
from rest_framework import serializers

from world.events.models import Event, EventHost, EventInvitation, EventModification
from world.roster.models import RosterEntry
from world.scenes.constants import PersonaType


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
        target = obj.get_active_target()
        return target.name if target else None


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
    is_host = serializers.SerializerMethodField()

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
            "is_host",
        ]
        read_only_fields = fields

    def get_is_host(self, obj: Event) -> bool:
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        active_entries = RosterEntry.objects.for_account(request.user)
        return obj.hosts.filter(
            persona__character__roster_entry__in=active_entries,
            persona__persona_type=PersonaType.PRIMARY,
        ).exists()


class EventUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating events. Only mutable fields are writable."""

    scheduled_ic_time = serializers.DateTimeField(required=False)

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

    def validate_scheduled_real_time(self, value: datetime) -> datetime:
        if value <= timezone.now():
            msg = "Scheduled time must be in the future."
            raise serializers.ValidationError(msg)
        return value


class EventCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating events. Host is derived from the request."""

    scheduled_ic_time = serializers.DateTimeField(required=False)

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
