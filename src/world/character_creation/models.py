"""
Character Creation models.

Models for the staged character creation flow:
- StartingArea: Selectable origin locations that gate heritage options
- SpecialHeritage: Special origin types (Sleeper, Misbegotten) that bypass normal family
- CharacterDraft: In-progress character creation state
"""

from datetime import timedelta

from django.db import models
from django.utils import timezone
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper.models import SharedMemoryModel

from world.traits.constants import PrimaryStat

# Primary stat constants
STAT_MIN_VALUE = 10  # Minimum stat value (displays as 1)
STAT_MAX_VALUE = 50  # Maximum stat value during character creation (displays as 5)
STAT_DISPLAY_DIVISOR = 10  # Divisor for display value (internal 20 = display 2)
STAT_DEFAULT_VALUE = 20  # Default starting value (displays as 2)
STAT_FREE_POINTS = 5  # Free points to distribute during character creation
STAT_BASE_POINTS = 16  # Base points (8 stats × 2)
STAT_TOTAL_BUDGET = STAT_BASE_POINTS + STAT_FREE_POINTS  # Total allocation budget (21)

# Required primary stat names
REQUIRED_STATS = PrimaryStat.get_all_stat_names()


class StartingArea(SharedMemoryModel):
    """
    A starting location/city that players can select in character creation.

    Each area gates which heritage options, species, and families are available.
    Maps to an Evennia room for character starting location.

    Note: Rooms may be None during early testing before grid is built.
    """

    class AccessLevel(models.TextChoices):
        ALL = "all", "All Players"
        TRUST_REQUIRED = "trust_required", "Trust Required"
        STAFF_ONLY = "staff_only", "Staff Only"

    # Canonical realm this StartingArea references (data lives in `realms.Realm`)
    realm = models.ForeignKey(
        "realms.Realm",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="starting_areas",
        help_text="Canonical realm/area referenced by this StartingArea (realms app).",
    )

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Display name of the starting area (e.g., 'Arx')",
    )
    description = models.TextField(
        help_text="Rich description shown on hover/click in character creation",
    )
    crest_image = models.URLField(
        blank=True,
        null=True,
        help_text="Cloudinary URL for crest/flag image. Leave blank for gradient placeholder.",
    )
    default_starting_room = models.ForeignKey(
        ObjectDB,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="starting_area_default",
        help_text="Default Evennia room where characters from this area start. "
        "Can be None during early testing.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this area can be selected in character creation",
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display order in selection UI (lower = first)",
    )
    access_level = models.CharField(
        max_length=20,
        choices=AccessLevel.choices,
        default=AccessLevel.ALL,
        help_text="Who can select this area in character creation",
    )
    minimum_trust = models.IntegerField(
        default=0,
        help_text="Minimum trust required when access_level is 'trust_required'",
    )

    # M2M to special heritages available in this area
    special_heritages = models.ManyToManyField(
        "SpecialHeritage",
        blank=True,
        related_name="available_in_areas",
        help_text="Special heritage options available when selecting this area",
    )

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Starting Area"
        verbose_name_plural = "Starting Areas"

    def __str__(self):
        return self.name

    def is_accessible_by(self, account: AccountDB) -> bool:
        """Check if an account can select this starting area."""
        if not self.is_active:
            return False

        # Staff bypass all restrictions
        if account.is_staff:
            return True

        if self.access_level == self.AccessLevel.STAFF_ONLY:
            return False

        if self.access_level == self.AccessLevel.TRUST_REQUIRED:
            # TODO: Implement trust system - this will raise AttributeError until then
            try:
                account_trust = account.trust
            except AttributeError:
                msg = "Trust system not yet implemented on Account model"
                raise NotImplementedError(msg) from None
            return account_trust >= self.minimum_trust

        return True  # AccessLevel.ALL


class SpecialHeritage(SharedMemoryModel):
    """
    Character creation metadata for special heritage types.

    This model stores creation-time options and rules (species access, starting rooms).
    The canonical heritage data (name, description) lives in character_sheets.Heritage.
    """

    # Link to canonical Heritage model (contains name, description, family_display)
    heritage = models.OneToOneField(
        "character_sheets.Heritage",
        on_delete=models.CASCADE,
        related_name="creation_options",
        help_text="Canonical heritage this maps to",
    )

    allows_full_species_list = models.BooleanField(
        default=True,
        help_text="If True, players can select any species instead of restricted list",
    )
    starting_room_override = models.ForeignKey(
        ObjectDB,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="special_heritage_start",
        help_text="Override starting room for this heritage",
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display order in selection UI (lower = first)",
    )

    class Meta:
        ordering = ["sort_order"]
        verbose_name = "Special Heritage Option"
        verbose_name_plural = "Special Heritage Options"

    def __str__(self):
        return f"Special Heritage: {self.heritage}"


class CharacterDraft(models.Model):
    """
    In-progress character creation state.

    Stores all staged data as JSON, allowing players to leave and return
    without losing progress. Drafts expire after 2 months of account inactivity.
    """

    class Stage(models.IntegerChoices):
        ORIGIN = 1, "Origin"
        HERITAGE = 2, "Heritage"
        LINEAGE = 3, "Lineage"
        ATTRIBUTES = 4, "Attributes"
        PATH_SKILLS = 5, "Path & Skills"
        TRAITS = 6, "Traits"
        IDENTITY = 7, "Identity"
        REVIEW = 8, "Review"

    # Ownership
    account = models.ForeignKey(
        AccountDB,
        on_delete=models.CASCADE,
        related_name="character_drafts",
        help_text="Account creating this character",
    )
    # TODO: Add table FK when Table model exists
    # table = models.ForeignKey(
    #     "tables.Table",
    #     on_delete=models.SET_NULL,
    #     null=True,
    #     blank=True,
    #     help_text="GM table this character is being created for (staff/GM only)",
    # )

    # Stage tracking
    current_stage = models.PositiveSmallIntegerField(
        choices=Stage.choices,
        default=Stage.ORIGIN,
        help_text="Current stage in character creation flow",
    )

    # Stage 1: Origin
    selected_area = models.ForeignKey(
        StartingArea,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drafts",
        help_text="Selected starting area",
    )

    # Stage 2: Heritage
    selected_heritage = models.ForeignKey(
        SpecialHeritage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drafts",
        help_text="Selected special heritage (null = normal upbringing)",
    )

    # Reference canonical species/gender options
    selected_species = models.ForeignKey(
        "character_sheets.Species",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drafts",
        help_text="Selected species",
    )
    selected_gender = models.ForeignKey(
        "character_sheets.Gender",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drafts",
        help_text="Selected gender",
    )

    age = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Character age in years",
    )

    # Stage 3: Lineage
    family = models.ForeignKey(
        "roster.Family",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="character_drafts",
        help_text="Selected family (null for orphan or special heritage).",
    )
    # Note: orphan intent can be represented in draft_data to avoid extra boolean field.

    # Stage 4-7: Complex data stored as JSON
    draft_data = models.JSONField(
        default=dict,
        help_text="Staged data: stats, skills, traits, identity, etc.",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Character Draft"
        verbose_name_plural = "Character Drafts"

    def __str__(self):
        name = self.draft_data.get("first_name", "Unnamed")
        account_name = self.account.username if self.account else "No Account"
        return f"Draft: {name} ({account_name})"

    @property
    def is_expired(self) -> bool:
        """Check if draft has expired due to account inactivity."""
        # Staff drafts don't expire
        if self.account and self.account.is_staff:
            return False

        # Expire after 2 months of no updates
        expiry_threshold = timezone.now() - timedelta(days=60)
        return self.updated_at < expiry_threshold

    def get_starting_room(self):
        """
        Resolve the starting room for this character.

        Priority:
        1. Special heritage's starting_room_override
        2. Starting area's default_starting_room
        3. None (valid for Evennia, used during early testing)
        """
        if self.selected_heritage and self.selected_heritage.starting_room_override:
            return self.selected_heritage.starting_room_override

        if self.selected_area and self.selected_area.default_starting_room:
            return self.selected_area.default_starting_room

        return None

    def get_stage_completion(self) -> dict[int, bool]:
        """
        Check completion status of each stage.

        Returns dict mapping stage number to completion boolean.
        """
        return {
            self.Stage.ORIGIN: self.selected_area is not None,
            self.Stage.HERITAGE: self._is_heritage_complete(),
            self.Stage.LINEAGE: self._is_lineage_complete(),
            self.Stage.ATTRIBUTES: self._is_attributes_complete(),
            self.Stage.PATH_SKILLS: self._is_path_skills_complete(),
            self.Stage.TRAITS: self._is_traits_complete(),
            self.Stage.IDENTITY: self._is_identity_complete(),
            self.Stage.REVIEW: False,  # Review is never "complete" - it's the final step
        }

    def _is_heritage_complete(self) -> bool:
        """Check if heritage stage is complete."""
        return bool(self.selected_species and self.selected_gender and self.age)

    def _is_lineage_complete(self) -> bool:
        """Check if lineage stage is complete."""
        # Special heritage = always complete (family is "Unknown")
        if self.selected_heritage:
            return True
        # Family chosen completes lineage
        if self.family is not None:
            return True
        # Allow marking orphan intent inside draft_data to avoid extra boolean field
        return bool(self.draft_data.get("lineage_is_orphan", False))

    def _calculate_stats_free_points(self) -> int:
        """
        Calculate remaining free points from stat allocations.

        Starting budget:
        - Base: 8 stats × 2 = 16 points
        - Free: 5 points
        - Total: 21 points

        Current spend: sum(stats.values()) / 10
        Remaining: 21 - spent

        Returns:
            Number of free points remaining (can be negative if over budget)
        """
        stats = self.draft_data.get("stats", {})
        if not stats:
            return STAT_FREE_POINTS  # All free points available

        spent = sum(stats.values()) / STAT_DISPLAY_DIVISOR
        return int(STAT_TOTAL_BUDGET - spent)

    def _is_attributes_complete(self) -> bool:
        """
        Check if attributes stage is complete.

        Validation rules:
        - All 8 stats must exist
        - All stat values must be integers
        - All stat values must be multiples of 10
        - All stats must be in 1-5 range (10-50 internal)
        - Free points must be exactly 0

        Returns:
            True if attributes stage is complete, False otherwise
        """
        stats = self.draft_data.get("stats", {})

        # All 8 stats must exist
        if not all(stat in stats for stat in REQUIRED_STATS):
            return False

        # Validate each stat value
        for value in stats.values():
            # Must be an integer
            if not isinstance(value, int):
                return False
            # Must be a multiple of 10
            if value % STAT_DISPLAY_DIVISOR != 0:
                return False
            # Must be in valid range (10-50)
            if not (STAT_MIN_VALUE <= value <= STAT_MAX_VALUE):
                return False

        # Free points must be exactly 0
        free_points = self._calculate_stats_free_points()
        return free_points == 0

    def _is_path_skills_complete(self) -> bool:
        """Check if path & skills stage is complete."""
        # TODO: Implement when path/skills system exists
        return bool(self.draft_data.get("path_skills_complete", False))

    def _is_traits_complete(self) -> bool:
        """Check if traits stage is complete."""
        # TODO: Implement when traits system exists
        return bool(self.draft_data.get("traits_complete", False))

    def _is_identity_complete(self) -> bool:
        """Check if identity stage is complete."""
        data = self.draft_data
        return bool(data.get("first_name") and data.get("description"))

    def can_submit(self) -> bool:
        """Check if all required stages are complete for submission."""
        completion = self.get_stage_completion()
        # All stages except REVIEW must be complete
        required_stages = [s for s in self.Stage if s != self.Stage.REVIEW]
        return all(completion.get(stage, False) for stage in required_stages)
