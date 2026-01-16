"""
Character Creation models.

Models for the staged character creation flow:
- StartingArea: Selectable origin locations that gate heritage options
- Beginnings: Worldbuilding paths (e.g., Sleeper, Normal Upbringing) for each area
- SpeciesOption: Makes a SpeciesOrigin available in a StartingArea with CG costs/permissions
- CharacterDraft: In-progress character creation state

Note: SpeciesOrigin and SpeciesOriginStatBonus are in the species app since they're
permanent character data (lore), not CG-specific mechanics.
"""

from datetime import timedelta

from django.core.validators import MaxValueValidator, MinValueValidator
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

# Age constraints for character creation
AGE_MIN = 18
AGE_MAX = 65
STAT_TOTAL_BUDGET = STAT_BASE_POINTS + STAT_FREE_POINTS  # Total allocation budget (21)

# Required primary stat names
REQUIRED_STATS = PrimaryStat.get_all_stat_names()


class CGPointBudgetManager(models.Manager["CGPointBudget"]):
    """Manager for CGPointBudget model with natural key support."""

    def get_by_natural_key(self, name: str) -> "CGPointBudget":
        return self.get(name=name)


class CGPointBudget(SharedMemoryModel):
    """
    Global CG point budget configuration.

    Single-row model for configuring the character creation point budget.
    Staff can change this without code changes.
    """

    name = models.CharField(
        max_length=100,
        default="Default Budget",
        help_text="Name for this budget configuration",
    )
    starting_points = models.IntegerField(
        default=100,
        help_text="Starting CG points for character creation",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this budget is currently active",
    )

    objects = CGPointBudgetManager()

    class Meta:
        verbose_name = "CG Point Budget"
        verbose_name_plural = "CG Point Budgets"

    def __str__(self):
        active = " (Active)" if self.is_active else ""
        return f"{self.name}: {self.starting_points} points{active}"

    @classmethod
    def get_active_budget(cls) -> int:
        """Get the current active CG point budget."""
        budget = cls.objects.filter(is_active=True).first()
        return budget.starting_points if budget else 100

    def natural_key(self) -> tuple[str]:
        return (self.name,)


class StartingAreaManager(models.Manager["StartingArea"]):
    """Manager for StartingArea model with natural key support."""

    def get_by_natural_key(self, name: str) -> "StartingArea":
        return self.get(name=name)


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

    objects = StartingAreaManager()

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

    def natural_key(self) -> tuple[str]:
        return (self.name,)


class SpeciesOptionManager(models.Manager["SpeciesOption"]):
    """Manager for SpeciesOption model with natural key support."""

    def get_by_natural_key(
        self, species_name: str, origin_name: str, area_name: str
    ) -> "SpeciesOption":
        return self.get(
            species_origin__species__name=species_name,
            species_origin__name=origin_name,
            starting_area__name=area_name,
        )


class SpeciesOption(SharedMemoryModel):
    """
    Makes a SpeciesOrigin available in a StartingArea with CG costs/permissions.

    This model contains only CG-specific mechanics (costs, permissions, availability).
    The permanent character data (stat bonuses, cultural description) lives in
    SpeciesOrigin in the species app.

    The same SpeciesOrigin can be made available in multiple StartingAreas with
    different costs and access requirements.
    """

    species_origin = models.ForeignKey(
        "species.SpeciesOrigin",
        on_delete=models.CASCADE,
        related_name="cg_options",
        help_text="The species origin being made available",
    )
    starting_area = models.ForeignKey(
        StartingArea,
        on_delete=models.CASCADE,
        related_name="species_options",
        help_text="The starting area where this option is available",
    )

    # Access Control
    trust_required = models.PositiveIntegerField(
        default=0,
        help_text="Minimum trust level required (0 = all players)",
    )
    is_available = models.BooleanField(
        default=True,
        help_text="Staff toggle to enable/disable this option",
    )

    # Costs & Display
    cg_point_cost = models.IntegerField(
        default=0,
        help_text="CG point cost for selecting this species option",
    )
    description_override = models.TextField(
        blank=True,
        help_text="CG-specific description override (uses species_origin.description if blank)",
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display order in selection UI (lower = first)",
    )

    objects = SpeciesOptionManager()

    # Starting Languages (simple M2M - starting languages are always full fluency)
    starting_languages = models.ManyToManyField(
        "species.Language",
        blank=True,
        related_name="species_options",
        help_text="Languages characters start with (full fluency)",
    )

    class Meta:
        verbose_name = "Species Option"
        verbose_name_plural = "Species Options"
        unique_together = [["species_origin", "starting_area"]]

    def __str__(self):
        return f"{self.species_origin.name} ({self.starting_area.name})"

    @property
    def display_description(self) -> str:
        """Return CG-specific description or fall back to species origin description."""
        return self.description_override or self.species_origin.description

    @property
    def species(self):
        """Convenience accessor to get the underlying Species."""
        return self.species_origin.species

    def is_accessible_by(self, account) -> bool:
        """
        Check if an account can select this species option.

        Args:
            account: The account to check access for

        Returns:
            True if the account can select this option
        """
        if not self.is_available:
            return False

        # Staff bypass all restrictions
        if account.is_staff:
            return True

        # Check trust requirement
        if self.trust_required > 0:
            try:
                account_trust = account.trust
            except AttributeError:
                # Trust system not yet implemented, allow if trust_required is 0
                return self.trust_required == 0
            return account_trust >= self.trust_required

        return True

    def get_stat_bonuses_dict(self) -> dict[str, int]:
        """
        Return stat bonuses from the species origin.

        Returns:
            Dict mapping stat names to bonus values, e.g., {"strength": 1, "agility": -1}
        """
        return self.species_origin.get_stat_bonuses_dict()

    def natural_key(self) -> tuple[str, str, str]:
        return (
            self.species_origin.species.name,
            self.species_origin.name,
            self.starting_area.name,
        )

    natural_key.dependencies = [  # type: ignore[attr-defined]
        "species.SpeciesOrigin",
        "character_creation.StartingArea",
    ]


class BeginningsManager(models.Manager["Beginnings"]):
    """Manager for Beginnings model with natural key support."""

    def get_by_natural_key(self, area_name: str, name: str) -> "Beginnings":
        return self.get(starting_area__name=area_name, name=name)


class Beginnings(SharedMemoryModel):
    """
    Character creation worldbuilding paths for each starting area.

    Replaces SpecialHeritage with a universal system that provides worldbuilding
    context for all paths (not just special ones). Each Beginnings option can
    gate which species are available and whether family is selectable.

    Examples:
    - Arx: "Normal Upbringing", "Sleeper", "Misbegotten"
    - Umbros: "Noble Birth", "Military Caste", "Servant Class"
    - Luxen: "Patrician Elite", "Merchant Class", "Khati Underclass"
    """

    name = models.CharField(
        max_length=100,
        help_text="Display name (e.g., 'Sleeper', 'Noble Birth')",
    )
    description = models.TextField(
        help_text="Worldbuilding text shown to players",
    )
    art_image = models.URLField(
        blank=True,
        help_text="URL for visual presentation",
    )
    starting_area = models.ForeignKey(
        StartingArea,
        on_delete=models.CASCADE,
        related_name="beginnings",
        help_text="The starting area this option belongs to",
    )
    trust_required = models.IntegerField(
        default=0,
        help_text="Minimum trust level required to see/select this option",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Staff toggle to enable/disable this option",
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display order in selection UI (lower = first)",
    )
    allows_all_species = models.BooleanField(
        default=False,
        help_text="If True, all species for the area are available (Sleeper/Misbegotten)",
    )
    family_known = models.BooleanField(
        default=True,
        help_text="Whether family is selectable in Lineage stage (False = 'Unknown')",
    )
    species_options = models.ManyToManyField(
        SpeciesOption,
        blank=True,
        related_name="beginnings",
        help_text="Species options available when allows_all_species is False",
    )

    objects = BeginningsManager()

    social_rank = models.IntegerField(
        default=0,
        help_text="Staff-only rank for determining noble/commoner/royal (not exposed to players)",
    )
    cg_point_cost = models.IntegerField(
        default=0,
        help_text="CG point cost for selecting this option (added to species cost)",
    )
    starting_room_override = models.ForeignKey(
        ObjectDB,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="beginnings_start",
        help_text="Override starting room for this Beginnings path (e.g., Sleeper wake room)",
    )

    class Meta:
        verbose_name = "Beginnings"
        verbose_name_plural = "Beginnings"
        unique_together = [["starting_area", "name"]]

    def __str__(self):
        return f"{self.name} ({self.starting_area.name})"

    def is_accessible_by(self, account) -> bool:
        """Check if an account can see/select this option."""
        if not self.is_active:
            return False

        if account.is_staff:
            return True

        if self.trust_required > 0:
            try:
                account_trust = account.trust
            except AttributeError:
                return self.trust_required == 0
            return account_trust >= self.trust_required

        return True

    def natural_key(self) -> tuple[str, str]:
        return (self.starting_area.name, self.name)

    natural_key.dependencies = ["character_creation.StartingArea"]  # type: ignore[attr-defined]


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
        APPEARANCE = 7, "Appearance"
        IDENTITY = 8, "Identity"
        REVIEW = 9, "Review"

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
    selected_beginnings = models.ForeignKey(
        "Beginnings",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drafts",
        help_text="Selected beginnings path",
    )

    # Species option (species origin + starting area + CG costs)
    selected_species_option = models.ForeignKey(
        SpeciesOption,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drafts",
        help_text="Selected species option with costs and bonuses",
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
        validators=[MinValueValidator(AGE_MIN), MaxValueValidator(AGE_MAX)],
        help_text=f"Character age in years ({AGE_MIN}-{AGE_MAX})",
    )

    # Stage 3: Lineage (merged into Heritage in new flow)
    family = models.ForeignKey(
        "roster.Family",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="character_drafts",
        help_text="Selected family (null for orphan or special heritage).",
    )
    # Family member position (NEW: for family tree system)
    family_member = models.ForeignKey(
        "roster.FamilyMember",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drafts",
        help_text="Family member position this character is filling",
    )
    # Note: orphan intent can be represented in draft_data to avoid extra boolean field.

    # Stage 7: Appearance
    height_band = models.ForeignKey(
        "forms.HeightBand",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drafts",
        help_text="Selected height band for CG",
    )
    height_inches = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Exact height in inches within the selected band",
    )
    build = models.ForeignKey(
        "forms.Build",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drafts",
        help_text="Selected build type",
    )

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
        Determine the starting room for this character.

        Priority:
        1. Beginnings starting_room_override (e.g., Sleeper wake room)
        2. StartingArea default_starting_room
        3. None (valid for Evennia, used during early testing)
        """
        if self.selected_beginnings and self.selected_beginnings.starting_room_override:
            return self.selected_beginnings.starting_room_override

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
            self.Stage.APPEARANCE: self._is_appearance_complete(),
            self.Stage.IDENTITY: self._is_identity_complete(),
            self.Stage.REVIEW: False,  # Review is never "complete" - it's the final step
        }

    def _is_heritage_complete(self) -> bool:
        """
        Check if heritage stage is complete.

        Validation rules (new combined Heritage + Lineage stage):
        - Must have species option selected
        - Must have gender and age
        - Must have family selection OR orphan flag OR special heritage
        - CG points must be non-negative (within budget)
        - Species option must be compatible with selected area
        - Species option must be accessible by user's trust level
        """
        # Required selections
        has_selections = bool(self.selected_species_option and self.selected_gender)

        # Family requirement (same as old lineage stage)
        family_complete = bool(
            (self.selected_beginnings and not self.selected_beginnings.family_known)
            or self.family
            or self.draft_data.get("lineage_is_orphan")
        )

        # CG points valid (must not be over budget)
        points_valid = self.calculate_cg_points_remaining() >= 0

        # Species-area compatibility and access checks
        if self.selected_species_option and self.selected_area:
            area_match = self.selected_species_option.starting_area == self.selected_area
            # Trust check requires account
            try:
                trust_ok = self.selected_species_option.is_accessible_by(self.account)
            except NotImplementedError:
                # Trust system not yet implemented, allow all
                trust_ok = True
        else:
            area_match = False
            trust_ok = False

        return has_selections and family_complete and points_valid and area_match and trust_ok

    def _is_lineage_complete(self) -> bool:
        """Check if lineage stage is complete."""
        # Beginnings with family_known=False = always complete (family is "Unknown")
        if self.selected_beginnings and not self.selected_beginnings.family_known:
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

    def calculate_cg_points_spent(self) -> int:
        """
        Calculate total CG points spent across all categories.

        Returns:
            Total CG points spent (sum of all 'spent' categories)
        """
        cg_data = self.draft_data.get("cg_points", {})
        spent = cg_data.get("spent", {})
        return sum(spent.values())

    def calculate_cg_points_remaining(self) -> int:
        """
        Calculate remaining CG points.

        Returns:
            Number of CG points remaining (can be negative if over budget)
        """
        starting = CGPointBudget.get_active_budget()
        spent = self.calculate_cg_points_spent()
        return starting - spent

    def get_stat_bonuses_from_heritage(self) -> dict[str, int]:
        """
        Get stat bonuses from selected species-area combination.

        Returns:
            Dict mapping stat names to bonus values (e.g., {"strength": 1})
        """
        if not self.selected_species_option:
            return {}
        return self.selected_species_option.get_stat_bonuses_dict()

    def calculate_final_stats(self) -> dict[str, int]:
        """
        Calculate final stat values including species bonuses.

        Final stats = allocated points + species bonuses (converted to internal scale).

        Returns:
            Dict mapping stat names to final internal values (10-50+ scale)
        """
        allocated = self.draft_data.get("stats", {})
        bonuses = self.get_stat_bonuses_from_heritage()

        final_stats = {}
        for stat_name in REQUIRED_STATS:
            base = allocated.get(stat_name, STAT_DEFAULT_VALUE)
            bonus = bonuses.get(stat_name, 0) * 10  # Convert to internal scale
            final_stats[stat_name] = base + bonus

        return final_stats

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

    def _is_appearance_complete(self) -> bool:
        """Check if appearance stage is complete."""
        return bool(
            self.age is not None
            and self.height_band is not None
            and self.height_inches is not None
            and self.build is not None
        )

    def _is_identity_complete(self) -> bool:
        """Check if identity stage is complete."""
        data = self.draft_data
        return bool(data.get("first_name"))

    def can_submit(self) -> bool:
        """Check if all required stages are complete for submission."""
        completion = self.get_stage_completion()
        # All stages except REVIEW must be complete
        required_stages = [s for s in self.Stage if s != self.Stage.REVIEW]
        return all(completion.get(stage, False) for stage in required_stages)
