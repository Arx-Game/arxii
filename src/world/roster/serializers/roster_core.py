"""
Roster and RosterEntry serializers for the roster system.
"""

from typing import ClassVar

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers

from web.api.character_type import derive_character_type
from world.roster.models import NPCLoan, Roster, RosterEntry
from world.roster.models.choices import RosterType
from world.roster.serializers.characters import CharacterSerializer
from world.roster.serializers.tenures import RosterTenureSerializer
from world.roster.services.gallery import portrait_url
from world.roster.services.presence import room_name, session_count


class RosterEntrySerializer(serializers.ModelSerializer):
    """Serialize roster entry data with nested character info."""

    character = CharacterSerializer(read_only=True, source="character_sheet.character")
    # #4151: the worn look's crop, and nothing for a visitor without an account (#3904).
    profile_picture_url = serializers.SerializerMethodField()
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
            "profile_picture_url",
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

    def get_profile_picture_url(self, obj: RosterEntry) -> str | None:
        """The worn look's crop; None for a visitor without an account (#3904, #4151)."""
        request = self.context.get("request")
        if request is None or not request.user.is_authenticated:
            return None
        return portrait_url(obj)

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


class MyNPCLoanSerializer(serializers.Serializer):
    """The loan an account plays a borrowed NPC under (#4418)."""

    id = serializers.IntegerField(read_only=True)
    scene_title = serializers.CharField(read_only=True, allow_null=True)
    offered_by_name = serializers.CharField(read_only=True)


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
    # #3774 -- cross-device attention. The three fields below are one
    # `AccountAttention` computed once per request by `mine()` and handed in
    # through serializer context, never a per-row query and never a memo on
    # the serializer (ADR-0260). Each getter's own docstring below states
    # which callers do not populate that context and therefore read 0/False.
    unread_direct = serializers.SerializerMethodField()
    has_ambient_unread = serializers.SerializerMethodField()
    attention_as_of_id = serializers.SerializerMethodField()
    # #3412 slice 3 task 5 — display-only lifecycle state, the seam T4 left
    # open ("the exposure seam ... is left for a follow-up task"). A plain
    # CharField source, not an annotation — ``lifecycle_state`` is already a
    # real column on ``CharacterSheet`` (no query beyond the existing
    # ``character_sheet`` traversal every other field on this serializer
    # already does), unlike ``unread_narrative_count`` above which aggregates
    # a related table. Lets the Hall's OffscreenActsPlate branch on
    # CAPTURED/DEAD/RETIRED/UNKNOWN without a new endpoint. Deliberately does
    # NOT surface the unconscious overlay (that reads the conditions system,
    # not a sheet column) — recorded as a seam, not built here.
    lifecycle_state = serializers.CharField(
        source="character_sheet.lifecycle_state", read_only=True
    )
    # Lets the frontend split "My NPCs" (#3426) out of the general character
    # list without a second query -- the value is one of world.roster.models
    # .choices.RosterType (e.g. "NPC", "Active").
    roster_type = serializers.CharField(source="roster.roster_type", read_only=True)
    # High-level typeclass grouping (#3478) -- "PC" | "GM" | "STAFF", the same
    # mapping the account payload's AvailableCharacterSerializer uses. Lets the
    # GM-profile UI distinguish its own GM character from ordinary PCs.
    character_type = serializers.SerializerMethodField()
    # Character slots (#3996). The Hall decides a card's action from these:
    # PLAYER provenance freezes and thaws, anything else is given up; a frozen
    # character shows its thaw date and does not count against the slots.
    activity_state = serializers.CharField(source="character_sheet.activity_state", read_only=True)
    activity_requirement = serializers.CharField(read_only=True)
    creation_provenance = serializers.CharField(read_only=True)
    thaw_available_at = serializers.DateTimeField(
        source="character_sheet.activity_state_until", read_only=True, allow_null=True
    )
    # Presence is a server fact (#4321). A tab knows only the socket it opened,
    # so a second tab or device used to call a character who was standing in a
    # room "Not in the world". These two read the sessions puppeting the
    # character (``world.roster.services.presence``), never a column, and the
    # header chip, the Hall card and the world menu state presence from them
    # when the tab has no socket of its own. ``room_name`` is null while no
    # session puppets the character, whatever location Evennia left it in.
    session_count = serializers.SerializerMethodField()
    room_name = serializers.SerializerMethodField()
    # #4418: a borrowed NPC. ``loan`` names the scene and who lent it (by their GM
    # character, never an account); ``npc_notes`` is what the owner wrote for whoever
    # plays it. Both null on every character the account holds itself.
    # Filled in by ``to_representation`` from one loan lookup per row; as declared
    # fields they read None off the entry (it has no such attributes).
    loan = MyNPCLoanSerializer(read_only=True, allow_null=True)
    npc_notes = serializers.CharField(read_only=True, allow_null=True)
    # #4418: this character voices a crowd in combat. A list view passes the ids it
    # already knows in ``context["crowd_voice_entry_ids"]``; a single-entry path
    # (selected entry, freeze, thaw) asks once for its one entry.
    is_crowd_voice = serializers.SerializerMethodField()

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
            "unread_direct",
            "has_ambient_unread",
            "attention_as_of_id",
            "lifecycle_state",
            "roster_type",
            "character_type",
            "activity_state",
            "activity_requirement",
            "creation_provenance",
            "thaw_available_at",
            "session_count",
            "room_name",
            "loan",
            "npc_notes",
            "is_crowd_voice",
        )
        read_only_fields: ClassVar[tuple[str, ...]] = fields

    def _borrowed_loan(self, obj: RosterEntry) -> NPCLoan | None:
        """The requester's ACTIVE loan of ``obj``, from their cached loans.

        Only an NPC-shelf row can be borrowed, so nothing is read for any other row.
        """
        if obj.roster.roster_type != RosterType.NPC:
            return None
        request = self.context.get("request")
        user = request.user if request is not None else None
        if user is None or not user.is_authenticated:
            return None
        for loan in user.player_data.cached_npc_loans:
            if loan.roster_entry_id == obj.pk and loan.borrower_id == user.pk:
                return loan
        return None

    def to_representation(self, instance: RosterEntry) -> dict:
        """The row, with ``loan`` and ``npc_notes`` from a single loan lookup."""
        from world.roster.services.npc_lending import account_character_name  # noqa: PLC0415

        data = super().to_representation(instance)
        loan = self._borrowed_loan(instance)
        if loan is None:
            data["loan"] = None
            data["npc_notes"] = None
            return data
        data["loan"] = MyNPCLoanSerializer(
            {
                "id": loan.pk,
                "scene_title": loan.scene.name if loan.scene is not None else None,
                "offered_by_name": account_character_name(loan.offered_by),
            }
        ).data
        try:
            notes = loan.roster_entry.story_npc_settings.notes_for_player
        except ObjectDoesNotExist:
            notes = ""
        data["npc_notes"] = notes or None
        return data

    def get_character_type(self, obj: RosterEntry) -> str:
        return derive_character_type(obj.character_sheet.character)

    def get_is_crowd_voice(self, obj: RosterEntry) -> bool:
        known = self.context.get("crowd_voice_entry_ids")
        if known is not None:
            return obj.pk in known
        from world.combat.models import CombatOpponent  # noqa: PLC0415

        return CombatOpponent.objects.filter(
            voice_persona__character_sheet_id=obj.character_sheet_id
        ).exists()

    def get_session_count(self, obj: RosterEntry) -> int:
        """Sessions puppeting the character right now (#4321); 0 means not in the world."""
        return session_count(obj.character_sheet.character)

    def get_room_name(self, obj: RosterEntry) -> str | None:
        """The room the character stands in while puppeted (#4321), else None."""
        return room_name(obj.character_sheet.character)

    def get_profile_picture_url(self, obj: RosterEntry) -> str | None:
        """The worn look's cropped URL, or None (#4151)."""
        return portrait_url(obj)

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

    def get_unread_direct(self, obj: RosterEntry) -> int:
        """Poses aimed at this character's personas and not yet read.

        Only populated on `GET /api/roster/entries/mine/`, which computes
        attention for the whole list up front. `/api/user/`'s `selected_entry`
        and the `select` action's response reuse this same serializer but do
        not compute attention, so this reads 0 there, not a live count.
        """
        attention = self.context.get("character_attention")
        if attention is None:
            return 0
        entry = attention.by_character.get(obj.character_sheet_id)
        return entry.direct if entry else 0

    def get_has_ambient_unread(self, obj: RosterEntry) -> bool:
        """Whether a scene this character is still in has moved without them.

        Only populated on `GET /api/roster/entries/mine/`, which computes
        attention for the whole list up front. `/api/user/`'s `selected_entry`
        and the `select` action's response reuse this same serializer but do
        not compute attention, so this reads False there, not a live value.
        """
        attention = self.context.get("character_attention")
        if attention is None:
            return False
        entry = attention.by_character.get(obj.character_sheet_id)
        return bool(entry and entry.ambient)

    def get_attention_as_of_id(self, _obj: RosterEntry) -> int:
        """The newest pose the direct/ambient counts above already include.

        The same for every row in a `mine()` response (one `AccountAttention`
        per request), so the entry itself is unused; kept for the
        `SerializerMethodField` signature. The client drops session
        interactions at or below this id before adding its own live
        WebSocket delta, so the same pose is never counted twice.

        Only populated on `GET /api/roster/entries/mine/`, which computes
        attention for the whole list up front. `/api/user/`'s `selected_entry`
        and the `select` action's response reuse this same serializer but do
        not compute attention, so this reads 0 there, not a real watermark.
        """
        attention = self.context.get("character_attention")
        return attention.as_of_id if attention else 0


class SlotHolderSerializer(serializers.Serializer):
    """One occupant of an account's character slots (#3996); see ``SlotHolder``."""

    kind = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    roster_entry_id = serializers.IntegerField(read_only=True, allow_null=True)
    counts = serializers.BooleanField(read_only=True)
    activity = serializers.BooleanField(read_only=True)


class CharacterSlotsSerializer(serializers.Serializer):
    """An account's slot ledger (#3996); ``total`` is null for an exempt account."""

    total = serializers.IntegerField(read_only=True, allow_null=True)
    used = serializers.IntegerField(read_only=True)
    activity_total = serializers.IntegerField(read_only=True)
    activity_used = serializers.IntegerField(read_only=True)
    holders = SlotHolderSerializer(many=True, read_only=True)


class ReleasedEntryResultSerializer(serializers.Serializer):
    """Result of giving up a roster character (#3996): the entry is no longer
    the account's, so only its id and new shelf come back."""

    id = serializers.IntegerField(read_only=True)
    roster_type = serializers.CharField(source="roster.roster_type", read_only=True)


class DisconnectResultSerializer(serializers.Serializer):
    """Result of disconnecting a character everywhere (#4321): how many sessions closed."""

    closed = serializers.IntegerField(read_only=True)


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
            "joined_roster",
            "creation_provenance",
            "creation_provenance_display",
            "created_for_table_name",
        ]

    def get_is_available(self, obj):
        """Check if character is available for application."""
        return obj.accepts_applications


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

        if not obj.is_active or not obj.allow_applications:
            return 0
        return obj.entries.exclude(tenures__end_date__isnull=True).count()
