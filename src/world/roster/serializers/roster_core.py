"""
Roster and RosterEntry serializers for the roster system.
"""

from typing import ClassVar

from rest_framework import serializers

from world.roster.models import Roster, RosterEntry
from world.roster.serializers.characters import CharacterSerializer
from world.roster.serializers.media import TenureMediaSerializer
from world.roster.serializers.tenures import RosterTenureSerializer


class RosterEntrySerializer(serializers.ModelSerializer):
    """Serialize roster entry data with nested character info."""

    character = CharacterSerializer(read_only=True, source="character_sheet.character")
    profile_picture = TenureMediaSerializer(read_only=True)
    tenures = RosterTenureSerializer(many=True, read_only=True, source="cached_tenures")
    can_apply = serializers.SerializerMethodField()
    fullname = serializers.SerializerMethodField()
    quote = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    # Provenance / quality signal (#1506): staff-vetted vs a player-GM's table character.
    creation_provenance_display = serializers.CharField(
        source="get_creation_provenance_display", read_only=True
    )
    created_for_table_name = serializers.CharField(
        source="created_for_table.name", read_only=True, allow_null=True, default=None
    )

    class Meta:
        model = RosterEntry
        fields: ClassVar[tuple[str, ...]] = (
            "id",
            "character",
            "profile_picture",
            "tenures",
            "can_apply",
            "fullname",
            "quote",
            "description",
            "creation_provenance",
            "creation_provenance_display",
            "created_for_table_name",
        )
        read_only_fields: ClassVar[tuple[str, ...]] = fields

    def get_can_apply(self, obj):
        """Return whether the requester may apply to play this character."""

        request = self.context.get("request")
        return bool(
            request and request.user.is_authenticated and obj.accepts_applications,
        )

    def get_fullname(self, obj):
        """Character's full long name."""
        try:
            item_data = obj.character_sheet.character.item_data
            return item_data.longname or ""
        except AttributeError:
            return ""

    def get_quote(self, obj):
        """Character's quote."""
        try:
            item_data = obj.character_sheet.character.item_data
            return item_data.quote or ""
        except AttributeError:
            return ""

    def get_description(self, obj):
        """Character's current description."""
        try:
            item_data = obj.character_sheet.character.item_data
            return item_data.get_display_description() or ""
        except AttributeError:
            return ""


class MyRosterEntrySerializer(serializers.ModelSerializer):
    """Serialize a summary of a roster entry for account menus."""

    name = serializers.CharField(source="character_sheet.character.db_key")
    # ``character_id`` doubles as ``character_sheet_id`` because CharacterSheet
    # uses the ObjectDB pk as its primary key (OneToOne with primary_key=True).
    # Surfacing it here lets the frontend route per-character API calls (e.g.
    # the wardrobe page) without a second lookup.
    character_id = serializers.IntegerField(
        source="character_sheet.character_id",
        read_only=True,
    )
    profile_picture_url = serializers.SerializerMethodField()
    primary_persona_id = serializers.SerializerMethodField()
    active_persona_id = serializers.SerializerMethodField()
    unread_narrative_count = serializers.SerializerMethodField()
    # Lets the frontend split "My NPCs" (#3426) out of the general character
    # list without a second query -- the value is one of world.roster.models
    # .choices.RosterType (e.g. "NPC", "Active").
    roster_type = serializers.CharField(source="roster.roster_type", read_only=True)

    class Meta:
        model = RosterEntry
        fields: ClassVar[tuple[str, ...]] = (
            "id",
            "name",
            "character_id",
            "profile_picture_url",
            "primary_persona_id",
            "active_persona_id",
            "unread_narrative_count",
            "roster_type",
        )
        read_only_fields: ClassVar[tuple[str, ...]] = fields

    def get_profile_picture_url(self, obj: RosterEntry) -> str | None:
        """Return the cloudinary URL for the entry's profile picture, or None."""
        try:
            return obj.profile_picture.media.cloudinary_url
        except AttributeError:
            return None

    def get_primary_persona_id(self, obj: RosterEntry) -> int | None:
        """Return the PRIMARY persona's id, or None if none exists.

        Used by player-submission forms to attach a reporter_persona.
        """
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        try:
            return obj.character_sheet.primary_persona.pk
        except ObjectDoesNotExist:
            return None

    def get_active_persona_id(self, obj: RosterEntry) -> int | None:
        """The face currently worn — the durable ``active_persona`` (#981) if set,
        else the PRIMARY. Lets the top-bar switcher highlight the worn identity."""
        if obj.character_sheet.active_persona_id is not None:
            return obj.character_sheet.active_persona_id
        return self.get_primary_persona_id(obj)

    def get_unread_narrative_count(self, obj: RosterEntry) -> int:
        """Unread narrative tidings for this character (#3412 — the Hall).

        ``RosterEntryViewSet.mine`` annotates this via one aggregated query for
        the whole list; that annotation lands as a plain instance attribute, so
        prefer it when present (``obj.__dict__`` avoids GETATTR_LITERAL — see
        `OrgAppealViewSet._refetch` for the same idiom). Other callers (e.g. the
        #3412 ``select`` endpoint's ``selected_entry`` fragment) serialize a
        plain, unannotated ``RosterEntry`` — fall back to a direct count there,
        a single extra query on that single-object path only.
        """
        annotated = obj.__dict__.get("unread_narrative_count")
        if annotated is not None:
            return annotated

        from world.narrative.models import NarrativeMessageDelivery  # noqa: PLC0415

        return NarrativeMessageDelivery.objects.filter(
            recipient_character_sheet_id=obj.character_sheet_id,
            acknowledged_at__isnull=True,
        ).count()


class SelectEntryRequestSerializer(serializers.Serializer):
    """POST body for the #3412 character-selection endpoint.

    ``entry_id: null`` clears the selection; any other value must be one of
    the account's own current roster entries (validated in the service, not
    here — a foreign id is rejected uniformly, mirroring the persona
    set-active endpoint).
    """

    entry_id = serializers.IntegerField(min_value=1, allow_null=True)


class SelectedEntryResultSerializer(serializers.Serializer):
    """Result of the #3412 select/clear endpoint — the updated selection
    fragment, in the same shape ``/api/user/`` exposes it in.

    Both fields are ``allow_null`` because a clear (``entry_id: null``) returns
    ``player_data.selected_entry_id``/``selected_entry`` as ``None`` — DRF's
    ``Serializer.to_representation`` already emits ``null`` for a ``None``
    attribute regardless of this flag, but omitting it left drf-spectacular
    generating a non-nullable schema/TS type for a field that is genuinely
    nullable at runtime.
    """

    selected_entry_id = serializers.IntegerField(read_only=True, allow_null=True)
    selected_entry = MyRosterEntrySerializer(read_only=True, allow_null=True)


class RosterEntryListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing available roster entries to apply for.
    Automatically filters based on player permissions and eligibility.
    """

    character_name = serializers.CharField(
        source="character_sheet.character.db_key",
        read_only=True,
    )
    character_id = serializers.IntegerField(
        source="character_sheet.character.id",
        read_only=True,
    )
    roster_name = serializers.CharField(source="roster.name", read_only=True)
    roster_description = serializers.CharField(
        source="roster.description",
        read_only=True,
    )
    is_available = serializers.SerializerMethodField()
    trust_evaluation = serializers.SerializerMethodField()
    # Provenance / quality signal (#1506): staff-vetted vs a player-GM's table character.
    creation_provenance_display = serializers.CharField(
        source="get_creation_provenance_display", read_only=True
    )
    created_for_table_name = serializers.CharField(
        source="created_for_table.name", read_only=True, allow_null=True, default=None
    )

    class Meta:
        model = RosterEntry
        fields: ClassVar[list[str]] = [
            "id",
            "character_id",
            "character_name",
            "roster_name",
            "roster_description",
            "is_available",
            "trust_evaluation",
            "joined_roster",
            "creation_provenance",
            "creation_provenance_display",
            "created_for_table_name",
        ]

    def get_is_available(self, obj):
        """Check if character is available for application."""
        return obj.accepts_applications

    def get_trust_evaluation(self, _obj):
        """Get trust evaluation for this player/character combination."""
        request = self.context.get("request")
        if not request:
            return
        try:
            player_data = request.user.player_data
        except AttributeError:
            return
        if not player_data:
            return

        # TODO: Implement trust evaluation when trust system is ready
        # return TrustEvaluator.evaluate_player_for_character(
        #     request.user.player_data, obj.character
        # )
        return


class RosterListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing rosters with character counts.
    """

    available_count = serializers.SerializerMethodField()

    class Meta:
        model = Roster
        fields: ClassVar[list[str]] = [
            "id",
            "name",
            "description",
            "is_active",
            "allow_applications",
            "available_count",
        ]

    def get_available_count(self, obj):
        """
        Get count of available characters in this roster for the requesting player.
        """
        request = self.context.get("request")
        if not request:
            return 0
        try:
            player_data = request.user.player_data
        except AttributeError:
            return 0
        if not player_data:
            return 0

        # TODO: Filter based on player trust when trust system is implemented
        # For now, return count of all characters in active roster
        # This is a placeholder until trust system is implemented
        if not obj.is_active or not obj.allow_applications:
            return 0
        return obj.entries.exclude(tenures__end_date__isnull=True).count()
