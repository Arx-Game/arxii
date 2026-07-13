"""Serializers for the overworld travel API (#2352)."""

from __future__ import annotations

from rest_framework import serializers

from world.travel.models import (
    TravelHub,
    TravelMethod,
    Voyage,
    VoyageInvite,
    VoyageParticipant,
)


class TravelHubSerializer(serializers.ModelSerializer):
    """Serializer for TravelHub — public infrastructure."""

    id = serializers.IntegerField(source="room_profile_id", read_only=True)

    class Meta:
        model = TravelHub
        fields = [
            "id",
            "name",
            "description",
            "travel_modes",
            "is_transit_stop",
            "is_active",
        ]


class TravelMethodSerializer(serializers.ModelSerializer):
    """Serializer for TravelMethod."""

    class Meta:
        model = TravelMethod
        fields = [
            "id",
            "name",
            "description",
            "travel_mode",
            "base_speed",
            "ship_type_id",
            "is_default",
        ]


class VoyageParticipantSerializer(serializers.ModelSerializer):
    """Serializer for VoyageParticipant."""

    persona_name = serializers.CharField(source="persona.name", read_only=True)

    class Meta:
        model = VoyageParticipant
        fields = [
            "id",
            "persona_id",
            "persona_name",
            "joined_at",
            "left_at",
            "legs_traveled",
        ]


class VoyageInviteSerializer(serializers.ModelSerializer):
    """Serializer for VoyageInvite — the RSVP invitation."""

    target_persona_name = serializers.CharField(source="target_persona.name", read_only=True)
    invited_by_name = serializers.CharField(source="invited_by.name", read_only=True)
    voyage_destination = serializers.CharField(source="voyage.destination_hub.name", read_only=True)

    class Meta:
        model = VoyageInvite
        fields = [
            "id",
            "voyage_id",
            "target_persona_id",
            "target_persona_name",
            "invited_by_id",
            "invited_by_name",
            "response",
            "invited_at",
            "responded_at",
            "voyage_destination",
        ]


class VoyageSerializer(serializers.ModelSerializer):
    """Serializer for Voyage — includes nested participants and invites."""

    destination_name = serializers.CharField(source="destination_hub.name", read_only=True)
    origin_name = serializers.CharField(source="origin_hub.name", read_only=True)
    travel_method_name = serializers.CharField(source="travel_method.name", read_only=True)
    leader_name = serializers.CharField(source="leader.name", read_only=True)
    participants = VoyageParticipantSerializer(many=True, read_only=True)

    class Meta:
        model = Voyage
        fields = [
            "id",
            "leader_id",
            "leader_name",
            "status",
            "origin_name",
            "destination_name",
            "travel_method_id",
            "travel_method_name",
            "current_leg_index",
            "route_hubs",
            "participants",
            "started_at",
            "completed_at",
        ]
