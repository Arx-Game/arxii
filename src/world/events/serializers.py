from datetime import datetime

from django.utils import timezone
from rest_framework import serializers

from world.events.constants import InvitationTargetType
from world.events.models import Event, EventHost, EventInvitation, EventModification
from world.scenes.models import Scene


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
    is_gm = serializers.SerializerMethodField()

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
            "is_gm",
        ]
        read_only_fields = fields

    def get_is_gm(self, obj: Event) -> bool:
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return Scene.objects.filter(
            event=obj,
            is_active=True,
            participations__account=request.user,
            participations__is_gm=True,
        ).exists()

    def get_is_host(self, obj: Event) -> bool:
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        persona_ids = self.context.get("persona_ids", set())
        return any(h.persona_id in persona_ids for h in obj.hosts_cached)


class _EventScheduleMixin:
    """Shared validation for event scheduling fields."""

    scheduled_ic_time = serializers.DateTimeField(required=False)

    def validate_scheduled_real_time(self, value: datetime) -> datetime:
        if value <= timezone.now():
            msg = "Scheduled time must be in the future."
            raise serializers.ValidationError(msg)
        return value


class EventUpdateSerializer(_EventScheduleMixin, serializers.ModelSerializer):
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


class EventInviteSerializer(serializers.Serializer):
    """Serializer for creating invitations."""

    target_type = serializers.ChoiceField(choices=InvitationTargetType.choices)
    target_id = serializers.IntegerField()


class EventCreateSerializer(_EventScheduleMixin, serializers.ModelSerializer):
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
