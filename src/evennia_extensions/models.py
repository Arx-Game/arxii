"""
Extensions to Evennia models.
This app extends Evennia's core models rather than replacing them.
"""

from typing import Union

from allauth.account.models import EmailAddress
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.utils.functional import cached_property
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from evennia_extensions.constants import ExitKind, RoomEnclosure
from evennia_extensions.mixins import RelatedCacheClearingMixin
from server.conf.serversession import ServerSession
from world.areas.constants import GridOrigin
from world.roster.models import ApplicationStatus, ApprovalScope, RosterApplication

# Type for Evennia command callers - can be Account, Session, or ObjectDB instance
CallerType = Union[AccountDB, ObjectDB, ServerSession]

_OBJECTDB_MODEL = "objects.ObjectDB"


class MediaType(models.TextChoices):
    """Media type choices for both player uploads and staff-authored game art."""

    PHOTO = "photo", "Photo"
    PORTRAIT = "portrait", "Character Portrait"
    GALLERY = "gallery", "Gallery Image"
    BACKGROUND = "background", "Background"
    ILLUSTRATION = "illustration", "Illustration"


class PlayerData(RelatedCacheClearingMixin, SharedMemoryModel):
    """
    Extends Evennia's AccountDB with additional player data.
    Uses evennia_extensions pattern instead of replacing Account entirely.
    Replaces all ArxI attribute usage with proper model fields.
    """

    lethal_consequences_opt_in = models.BooleanField(
        default=False,
        help_text=(
            "OOC opt-in to lethal justice outcomes (#2378, ADR-0023). Without "
            "it, a PC's sentence caps below execution regardless of the case."
        ),
    )

    account = models.OneToOneField(
        AccountDB,
        on_delete=models.CASCADE,
        related_name="player_data",
        primary_key=True,
    )

    # Clear account's cached properties when player data changes
    related_cache_fields = ["account"]

    # Player preferences (replaces attributes like db.hide_from_watch)
    display_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="How they appear to others",
    )
    karma = models.PositiveIntegerField(default=0)
    rollmod = models.SmallIntegerField(default=0)
    hide_from_watch = models.BooleanField(default=False)
    private_mode = models.BooleanField(default=False)

    # Looking-for-table flag (#2431) — persistent profile flag a player sets
    # so GMs browsing for players can find them. Auto-clears on GMTable join.
    looking_for_table = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Player is looking for a GM table to join.",
    )
    looking_for_table_set_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the player set the looking-for-table flag (for GM browse sorting).",
    )

    # Staff data
    gm_notes = models.TextField(blank=True, help_text="Staff notes about player")

    # Session tracking (replaces attributes)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    # Media settings
    profile_picture = models.ForeignKey(
        "Media",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="profile_for_players",
        help_text="Profile picture for this account",
    )
    max_storage = models.PositiveIntegerField(
        default=0,
        help_text="Max number of media files this player may store",
    )
    max_file_size = models.PositiveIntegerField(
        default=0,
        help_text="Max upload size per file in KB",
    )

    # Timestamps
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    @property
    def avatar_url(self):
        if not self.profile_picture:
            return None
        return self.profile_picture.cloudinary_url

    @cached_property
    def cached_tenures(self):
        """Cached list of all tenures for this player. Use with prefetch_related."""
        return list(self.tenures.all())

    @property
    def cached_active_tenures(self):
        """List of currently active tenures for this player (uses cached data)."""
        return [tenure for tenure in self.cached_tenures if tenure.is_current]

    def get_available_characters(self):
        """Return characters this player is actively playing using cached data.

        #2287: retired (released) dead characters are excluded — the ghost
        interlude ends at retire, and the character can never be logged into
        again. Dead-but-unretired characters stay available (spectator ghost).
        """
        from world.vitals.services import is_retired  # noqa: PLC0415

        return [
            tenure.roster_entry.character_sheet.character
            for tenure in self.cached_active_tenures
            if tenure.roster_entry.roster.is_active
            and not is_retired(tenure.roster_entry.character_sheet)
        ]

    def get_seance_manifestable_characters(self):
        """Retired characters this player can manifest via an accepted, open seance (#2393).

        Disjoint from get_available_characters() — retired characters are
        always excluded there. This is the narrow companion list CmdIC also
        searches so `@ic <name>` can reach a retired honoree once their
        seance offer is accepted.
        """
        from world.ceremonies.constants import CeremonyStatus, SeanceOfferStatus  # noqa: PLC0415
        from world.ceremonies.models import SeanceManifestationOffer  # noqa: PLC0415
        from world.vitals.services import is_retired  # noqa: PLC0415

        result = []
        for tenure in self.cached_active_tenures:
            if not tenure.roster_entry.roster.is_active:
                continue
            sheet = tenure.roster_entry.character_sheet
            if not is_retired(sheet):
                continue
            has_accepted_open_offer = SeanceManifestationOffer.objects.filter(
                ceremony_honoree__honoree_sheet=sheet,
                status=SeanceOfferStatus.ACCEPTED,
                ceremony_honoree__ceremony__status=CeremonyStatus.OPEN,
            ).exists()
            if has_accepted_open_offer:
                result.append(sheet.character)
        return result

    def get_current_character(self):
        """Get the character this player is currently logged in as"""
        # This would be set when player switches characters via @ic command
        # For now, return the first available character if any
        characters = self.get_available_characters()
        return characters[0] if characters else None

    def get_pending_applications(self):
        """Get all pending applications for this player"""
        return RosterApplication.objects.filter(
            player_data=self,
            status=ApplicationStatus.PENDING,
        )

    def can_approve_applications(self):
        """Check if this player has any application approval permissions"""
        # This will integrate with the trust system when implemented
        # For now, just check if they're staff
        return self.account.is_staff

    def get_approval_scope(self):
        """Get the scope of applications this player can approve"""
        # This will return specific character types, houses, etc. when trust system
        # is implemented
        # For now, return all if staff, none otherwise
        if self.account.is_staff:
            return ApprovalScope.ALL
        return ApprovalScope.NONE

    def can_apply_for_characters(self):
        """
        Check if this player can apply for characters (requires email verification).
        """
        # Use allauth's email verification system
        try:
            email_address = EmailAddress.objects.get(
                user=self.account,
                email=self.account.email,
                primary=True,
            )
            return email_address.verified
        except EmailAddress.DoesNotExist:
            return False

    def __str__(self):
        return f"PlayerData for {self.account.username}"

    class Meta:
        verbose_name = "Player Data"
        verbose_name_plural = "Player Data"


class Artist(SharedMemoryModel):
    """Represents a player offering art commissions."""

    player_data = models.OneToOneField(
        PlayerData,
        on_delete=models.CASCADE,
        related_name="artist_profile",
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    commission_notes = models.TextField(blank=True)
    accepting_commissions = models.BooleanField(default=False)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Artist"
        verbose_name_plural = "Artists"


class Media(NaturalKeyMixin, SharedMemoryModel):
    """Cloudinary-backed image: player-uploaded media or staff-authored game art.

    Player-owned rows set ``player_data`` and leave ``slug`` null (created live
    via the player upload endpoint). Staff-authored rows leave ``player_data``
    null and set ``slug`` — addressed by natural key from the lore-repo content
    pipeline (#2408). "Owned by a player" is derived from ``player_data_id is
    not None``; there is deliberately no separate boolean/type flag for it.
    """

    player_data = models.ForeignKey(
        PlayerData,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="media",
        help_text="Owning player, for player-uploaded rows. Null for staff-authored art.",
    )
    slug = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        help_text="Natural-key identifier for staff-authored, content-pipeline-sourced rows. "
        "Null for player-uploaded media (never addressed by natural key).",
    )
    cloudinary_public_id = models.CharField(
        max_length=255,
        help_text="Cloudinary public ID for this media",
    )
    cloudinary_url = models.URLField(help_text="Full Cloudinary URL")
    media_type = models.CharField(
        max_length=20,
        choices=MediaType.choices,
        default=MediaType.PHOTO,
    )
    title = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        Artist,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_media",
        help_text="Artist who created this media",
    )
    uploaded_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["slug"]

    def __str__(self) -> str:
        title = self.title or "Untitled"
        owner = self.player_data.account.username if self.player_data_id else "staff"
        return f"{self.media_type} for {owner} ({title})"

    class Meta:
        ordering = ["-uploaded_date"]
        indexes = [models.Index(fields=["player_data", "media_type"])]


class PageBackgroundSlot(models.TextChoices):
    """Named page/area that can carry a staff-set background image."""

    HOMEPAGE = "homepage", "Homepage"
    ROSTER = "roster", "Roster"
    CG_STAGE = "cg_stage", "Character Creation"
    GAME_CLIENT = "game_client", "Game Client"


class PageBackground(NaturalKeyMixin, SharedMemoryModel):
    """Maps a named page slot to a background Media row (#2408).

    One row per slot; ``art`` is null-safe everywhere it's read (missing art
    falls back to the existing gradient-placeholder convention on the frontend).
    """

    slot = models.CharField(
        max_length=20,
        choices=PageBackgroundSlot.choices,
        unique=True,
    )
    art = models.ForeignKey(
        "Media",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="page_backgrounds",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["slot"]

    def __str__(self) -> str:
        return f"PageBackground({self.slot})"

    class Meta:
        verbose_name = "Page Background"
        verbose_name_plural = "Page Backgrounds"


class ObjectDisplayData(SharedMemoryModel):
    """
    Generic display data for any Evennia object.

    Provides customizable names, descriptions, and thumbnails that can be used
    by any object in the game (characters, rooms, items, etc.). This replaces
    the need for object-specific display models and allows unified handling
    of object presentation.
    """

    object = models.OneToOneField(
        _OBJECTDB_MODEL,
        on_delete=models.CASCADE,
        related_name="display_data",
        primary_key=True,
        help_text="The object this display data belongs to",
    )

    # Display names
    colored_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Name with color formatting codes",
    )
    longname = models.CharField(
        max_length=255,
        blank=True,
        help_text="Full object name with titles/descriptions",
    )

    # Descriptions
    permanent_description = models.TextField(
        blank=True,
        help_text="Object's permanent description",
    )
    temporary_description = models.TextField(
        blank=True,
        help_text="Temporary description (masks, illusions, etc.)",
    )

    # Visual representation
    thumbnail = models.ForeignKey(
        Media,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="thumbnailed_objects",
        help_text="Visual representation for this object",
    )

    # Timestamps
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    def get_display_description(self):
        """Get the appropriate description, with temporary overriding permanent."""
        return self.temporary_description or self.permanent_description or ""

    def get_display_name(self, include_colored=True):
        """
        Get the appropriate display name with fallback hierarchy.

        Args:
            include_colored (bool): Whether to include colored names

        Returns:
            str: The most appropriate display name
        """
        if include_colored and self.colored_name:
            return self.colored_name
        if self.longname:
            return self.longname
        return self.object.key

    def __str__(self):
        return f"Display data for {self.object.key}"

    class Meta:
        verbose_name = "Object Display Data"
        verbose_name_plural = "Object Display Data"


class PlayerAllowList(SharedMemoryModel):
    """
    Players this account allows to contact them (friends/allowlist).
    """

    owner = models.ForeignKey(
        PlayerData,
        on_delete=models.CASCADE,
        related_name="allow_list",
    )
    allowed_player = models.ForeignKey(
        PlayerData,
        on_delete=models.CASCADE,
        related_name="allowed_by",
    )
    added_date = models.DateTimeField(auto_now_add=True)
    notes = models.CharField(
        max_length=200,
        blank=True,
        help_text="Optional note about this player",
    )

    def __str__(self):
        owner_name = self.owner.account.username
        allowed_name = self.allowed_player.account.username
        return f"{owner_name} allows {allowed_name}"

    class Meta:
        unique_together = ["owner", "allowed_player"]
        verbose_name = "Player Allow List Entry"
        verbose_name_plural = "Player Allow List Entries"


# NOTE: the old account-level ``PlayerBlockList`` was removed (#1278) — it was unwired and is
# superseded by the persona-aware ``world.scenes.Block`` (block resolution lives there with the
# Persona FKs it needs). ``PlayerAllowList`` (above) stays — it's the allow/friends list, now wired
# by the #1271 privacy tiers.


class RoomSizeTier(NaturalKeyMixin, SharedMemoryModel):
    """A rung on the shared room-size unit ladder (#670; PLACEHOLDER magnitudes).

    Rooms spend these units from their building's space budget. The unit
    ladder is also the shared contract for the future creature-size stat
    (entry gating, combat range) — coordinate changes with that work.
    """

    name = models.CharField(max_length=40, unique=True)
    units = models.PositiveIntegerField(unique=True)

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["units"]

    def __str__(self) -> str:
        return f"{self.name} ({self.units} units)"


def room_is_publicly_listed(room: ObjectDB) -> bool:
    """Whether a room appears in public listings. Missing RoomProfile -> not public.

    Single source of truth for the scene privacy<->room-publicness invariant:
    consumed by Scene validation, ensure_scene_for_location, and combat duels.
    Story-area rooms are never publicly listed regardless of the ``is_public``
    flag — GM-authored areas (GridOrigin.STORY) are staff scaffolding, not
    content meant to surface in the global room listing.
    """
    try:
        profile = room.room_profile
    except ObjectDoesNotExist:
        return False
    if profile.area_id is not None and profile.area.origin == GridOrigin.STORY:
        return False
    return profile.is_public


class RoomProfile(NaturalKeyMixin, SharedMemoryModel):
    """Links an Evennia room to the spatial hierarchy.

    Thin extension model — only area FK for now. Future game systems
    (resonances, ownership, defenses) get their own models.
    """

    objectdb = models.OneToOneField(
        _OBJECTDB_MODEL,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="room_profile",
    )
    area = models.ForeignKey(
        "areas.Area",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="rooms",
    )
    is_public = models.BooleanField(
        default=True,
        help_text="Whether this room appears in public room listings",
    )
    is_social_hub = models.BooleanField(
        default=False,
        help_text=(
            "Whether this room is a social hub where gossip is planted/sought (#1572). "
            "Staff- or owner-designated; the foundation for the owner-upgradeable amplifier "
            "layer (#1694)."
        ),
    )
    is_outdoor = models.BooleanField(
        default=False,
        help_text=(
            "Whether this room is exposed to outdoor environment "
            "(weather, sky, etc.). Most rooms are indoor."
        ),
    )
    size = models.ForeignKey(
        "evennia_extensions.RoomSizeTier",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="rooms",
        help_text=(
            "Mechanical room size on the shared unit ladder (#670); spends from the "
            "building's space budget. NULL = unsized (wilderness / rooms outside the "
            "budget system)."
        ),
    )
    grid_x = models.SmallIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Building-local map column (#670). Cosmetic layout only — never gates "
            "creation or movement. NULL (with grid_y) = unplaced on the map."
        ),
    )
    grid_y = models.SmallIntegerField(
        null=True,
        blank=True,
        help_text="Building-local map row (#670). See grid_x; north renders as +y.",
    )
    floor = models.SmallIntegerField(
        default=0,
        help_text="Vertical level within the building (#670); 0 = ground, negative = below.",
    )
    enclosure = models.CharField(
        max_length=20,
        choices=RoomEnclosure.choices,
        default=RoomEnclosure.WALLED,
        help_text=(
            "How enclosed the room is (#1514). Gates which outdoor weather (rain/snow, wind) "
            "reaches inhabitants for comfort; temperature seeps regardless. Default WALLED = a "
            "normal indoor room; set OPEN_AIR/ROOFED for verandas and open courts."
        ),
    )
    # NOTE (#670): the old #676 ``tenant_persona`` pointer was removed —
    # ``locations.LocationTenancy`` is the one tenancy model (with
    # ``is_primary_home`` driving prestige_from_dwellings).
    default_blueprint = models.ForeignKey(
        "areas.PositionBlueprint",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="rooms_defaulting",
        help_text="Default terrain layout applied when this room initialises a position grid.",
    )
    fixture_key = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        help_text=(
            "Permanent stable identifier for authored (exported) rooms, e.g. "
            "'arx-city/golden-hart-taproom' (#2448). Required when origin=AUTHORED; "
            "NULL for player/instance rooms."
        ),
    )
    origin = models.CharField(
        max_length=16,
        choices=GridOrigin.choices,
        default=GridOrigin.PLAYER,
        db_index=True,
        help_text="Who authored this room — only AUTHORED rooms export (#2448).",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["fixture_key"]

    class Meta:
        verbose_name = "Room Profile"
        verbose_name_plural = "Room Profiles"

    def __str__(self):
        area_name = self.area.name if self.area else "unplaced"
        return f"RoomProfile for {self.objectdb.db_key} ({area_name})"


class ExitProfile(SharedMemoryModel):
    """Typed state for an Evennia Exit object.

    Mirrors ``RoomProfile``: a OneToOne Django model that adds queryable fields
    to an Evennia object without replacing the core typeclass. The first kind is
    ``WINDOW``, which can be opened/closed to affect traversal and room comfort.
    """

    objectdb = models.OneToOneField(
        _OBJECTDB_MODEL,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="exit_profile",
    )
    exit_kind = models.CharField(
        max_length=20,
        choices=ExitKind.choices,
        default=ExitKind.DOOR,
        help_text="What kind of exit this is.",
    )
    is_open = models.BooleanField(
        default=False,
        help_text="For WINDOW kinds: whether the window is open.",
    )

    class Meta:
        verbose_name = "Exit Profile"
        verbose_name_plural = "Exit Profiles"

    def __str__(self):
        return f"ExitProfile for {self.objectdb.db_key} ({self.exit_kind})"

    @classmethod
    def get_or_create_for_exit(cls, exit_obj):
        """Return the ExitProfile for an exit, creating a default DOOR row if absent."""
        return cls.objects.get_or_create(objectdb=exit_obj)[0]
