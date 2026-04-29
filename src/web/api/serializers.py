"""Serializers for the web API."""

from allauth.account.models import EmailAddress
from evennia.accounts.models import AccountDB
from rest_framework import serializers

from web.api.character_type import derive_character_type
from world.roster.models import RosterApplication, RosterEntry
from world.scenes.models import Persona


class PersonaPayloadSerializer(serializers.ModelSerializer):
    """Persona entry inside the account payload's available_characters."""

    display_name = serializers.SerializerMethodField()

    def get_display_name(self, obj: Persona) -> str:
        # Currently identical to name; reserved for future formatting (color codes, titles, etc.)
        return obj.name

    class Meta:
        model = Persona
        fields = ["id", "name", "persona_type", "display_name"]


class AvailableCharacterSerializer(serializers.Serializer):
    """An entry in the account payload's available_characters list.

    Input: a RosterEntry. Context must provide `puppeted_character_ids: set[int]`.
    """

    id = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()
    portrait_url = serializers.SerializerMethodField()
    character_type = serializers.SerializerMethodField()
    roster_status = serializers.CharField(source="roster.name", read_only=True)
    personas = serializers.SerializerMethodField()
    last_location = serializers.SerializerMethodField()
    currently_puppeted_in_session = serializers.SerializerMethodField()

    def get_id(self, obj: RosterEntry) -> int:
        return obj.character_sheet.character.id

    def get_name(self, obj: RosterEntry) -> str:
        return obj.character_sheet.character.key

    def get_portrait_url(self, obj: RosterEntry) -> str | None:
        if obj.profile_picture is None:
            return None
        # profile_picture is a TenureMedia; the underlying PlayerMedia carries the URL.
        return obj.profile_picture.media.cloudinary_url

    def get_character_type(self, obj: RosterEntry) -> str:
        return derive_character_type(obj.character_sheet.character)

    def get_personas(self, obj: RosterEntry) -> list[dict]:
        return PersonaPayloadSerializer(obj.character_sheet.cached_payload_personas, many=True).data

    def get_last_location(self, obj: RosterEntry) -> dict | None:
        location = obj.character_sheet.character.location
        if location is None:
            return None
        return {"id": location.id, "name": location.key}

    def get_currently_puppeted_in_session(self, obj: RosterEntry) -> bool:
        puppeted_ids = self.context.get("puppeted_character_ids", set())
        return obj.character_sheet.character.id in puppeted_ids


class PendingApplicationSerializer(serializers.ModelSerializer):
    """Pending RosterApplication entry for the account payload."""

    character_name = serializers.CharField(source="character.key", read_only=True)

    class Meta:
        model = RosterApplication
        fields = ["id", "character_name", "status", "applied_date"]


class AccountPlayerSerializer(serializers.ModelSerializer):
    """Serialize account and player display information."""

    display_name = serializers.CharField(
        source="player_data.display_name",
        read_only=True,
    )
    email_verified = serializers.SerializerMethodField()
    can_create_characters = serializers.SerializerMethodField()
    is_staff = serializers.BooleanField(read_only=True)
    avatar_url = serializers.SerializerMethodField()
    available_characters = serializers.SerializerMethodField()
    pending_applications = serializers.SerializerMethodField()

    def get_email_verified(self, obj):
        """Check if user's primary email is verified."""
        try:
            email_address = EmailAddress.objects.get(user=obj, primary=True)
            return email_address.verified
        except EmailAddress.DoesNotExist:
            return False

    def get_can_create_characters(self, obj):
        """Check if user can create new characters."""
        return obj.player_data.can_apply_for_characters()

    def get_avatar_url(self, obj):
        """Get player's avatar URL if available."""
        return obj.player_data.avatar_url

    def get_available_characters(self, _obj) -> list[dict]:
        """List of ACTIVE-roster characters playable by this account.

        Reads prefetched `active_entries` from serializer context. Build the
        context via `web.api.payload_helpers.build_account_payload_context`.
        """
        entries = self.context.get("active_entries", [])
        return AvailableCharacterSerializer(
            entries,
            many=True,
            context={
                "puppeted_character_ids": self.context.get("puppeted_character_ids", set()),
            },
        ).data

    def get_pending_applications(self, _obj) -> list[dict]:
        """Account's pending RosterApplications (from prefetched context)."""
        apps = self.context.get("pending_applications", [])
        return PendingApplicationSerializer(apps, many=True).data

    class Meta:
        model = AccountDB
        fields = [
            "id",
            "username",
            "display_name",
            "last_login",
            "email",
            "email_verified",
            "can_create_characters",
            "is_staff",
            "avatar_url",
            "available_characters",
            "pending_applications",
        ]
