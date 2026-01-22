"""
Character Creation models.

Models for the staged character creation flow:
- StartingArea: Selectable origin locations that gate heritage options
- Beginnings: Worldbuilding paths (e.g., Sleeper, Normal Upbringing) for each area
- CharacterDraft: In-progress character creation state
"""

from datetime import timedelta

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper.models import SharedMemoryModel
from rest_framework import serializers

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.classes.models import PathStage
from world.traits.constants import PrimaryStat

# Primary stat constants
STAT_MIN_VALUE = 10  # Minimum stat value (displays as 1)
STAT_MAX_VALUE = 50  # Maximum stat value during character creation (displays as 5)
STAT_DISPLAY_DIVISOR = 10  # Divisor for display value (internal 20 = display 2)
STAT_DEFAULT_VALUE = 20  # Default starting value (displays as 2)
STAT_FREE_POINTS = 5  # Free points to distribute during character creation
STAT_BASE_POINTS = 18  # Base points (9 stats × 2)

# Age constraints for character creation
AGE_MIN = 18
AGE_MAX = 65
STAT_TOTAL_BUDGET = STAT_BASE_POINTS + STAT_FREE_POINTS  # Total allocation budget (21)

# Required primary stat names
REQUIRED_STATS = PrimaryStat.get_all_stat_names()


class CGPointBudget(NaturalKeyMixin, SharedMemoryModel):
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

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

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


class StartingArea(NaturalKeyMixin, SharedMemoryModel):
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

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

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


class Beginnings(NaturalKeyMixin, SharedMemoryModel):
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
    family_known = models.BooleanField(
        default=True,
        help_text="Whether family is selectable in Lineage stage (False = 'Unknown')",
    )
    allowed_species = models.ManyToManyField(
        "species.Species",
        blank=True,
        related_name="beginnings",
        help_text="Species available for this path. Parent species include all children.",
    )
    starting_languages = models.ManyToManyField(
        "species.Language",
        blank=True,
        related_name="beginnings",
        help_text="Languages granted to all characters from this path",
    )
    grants_species_languages = models.BooleanField(
        default=True,
        help_text="If False, characters don't get species' racial language (Misbegotten)",
    )

    objects = NaturalKeyManager()

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

    class NaturalKeyConfig:
        fields = ["starting_area", "name"]
        dependencies = ["character_creation.StartingArea"]

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

    def get_available_species(self):
        """
        Get all species available for this Beginnings, expanding parents to children.

        If a parent species (e.g., Khati) is in allowed_species, all its children
        (Vulpi, Cani, etc.) are available. Leaf species are returned directly.

        Returns:
            QuerySet of Species that can be selected for this path
        """
        from world.species.models import Species  # noqa: PLC0415

        result_ids = set()
        for species in self.allowed_species.all():
            children = species.children.all()
            if children.exists():
                # Parent species - add all children
                result_ids.update(children.values_list("id", flat=True))
            else:
                # Leaf species - add directly
                result_ids.add(species.id)
        return Species.objects.filter(id__in=result_ids).order_by("sort_order", "name")

    def get_starting_languages(self, species):
        """
        Get starting languages for a character with this Beginnings and species.

        Args:
            species: The selected Species

        Returns:
            QuerySet of Language objects
        """
        from world.species.models import Language  # noqa: PLC0415

        language_ids = set(self.starting_languages.values_list("id", flat=True))
        if self.grants_species_languages:
            language_ids.update(species.starting_languages.values_list("id", flat=True))
        return Language.objects.filter(id__in=language_ids)


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

    selected_species = models.ForeignKey(
        "species.Species",
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

    # Stage 5: Path
    selected_path = models.ForeignKey(
        "classes.Path",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={"stage": PathStage.PROSPECT, "is_active": True},
        related_name="drafts",
        help_text="Selected starting path (Prospect stage only)",
    )

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

        Validation rules:
        - Must have beginnings selected
        - Must have species selected (and species must be allowed by beginnings)
        - Must have gender selected
        - Must have family selection OR orphan flag OR family_known=False
        - CG points must be non-negative (within budget)
        """
        # Required selections
        has_selections = bool(
            self.selected_beginnings and self.selected_species and self.selected_gender
        )

        # Family requirement
        family_complete = bool(
            (self.selected_beginnings and not self.selected_beginnings.family_known)
            or self.family
            or self.draft_data.get("lineage_is_orphan")
        )

        # CG points valid (must not be over budget)
        points_valid = self.calculate_cg_points_remaining() >= 0

        # Species must be allowed by beginnings
        if self.selected_beginnings and self.selected_species:
            available_species = self.selected_beginnings.get_available_species()
            species_valid = self.selected_species in available_species
        else:
            species_valid = False

        return has_selections and family_complete and points_valid and species_valid

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
        - Base: 9 stats × 2 = 18 points
        - Free: 5 points
        - Total: 23 points

        Current spend: sum(stats.values()) / 10
        Remaining: 23 - spent

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
        Get stat bonuses from selected species.

        Returns:
            Dict mapping stat names to bonus values (e.g., {"strength": 1})
        """
        if not self.selected_species:
            return {}
        return self.selected_species.get_stat_bonuses_dict()

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
        - All 9 stats must exist
        - All stat values must be integers
        - All stat values must be multiples of 10
        - All stats must be in 1-5 range (10-50 internal)
        - Free points must be exactly 0

        Returns:
            True if attributes stage is complete, False otherwise
        """
        stats = self.draft_data.get("stats", {})

        # All 9 stats must exist
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
        """
        Check Stage 5 (Path & Skills) completion status.

        Returns True if valid, False otherwise. For detailed error messages,
        use validate_path_skills() which raises ValidationError.
        """
        # Must have a path selected
        if not self.selected_path:
            return False

        try:
            self.validate_path_skills()
            return True
        except serializers.ValidationError:
            return False

    def validate_path_skills(self) -> None:
        """
        Validate Stage 5 (Path & Skills) data.

        Raises:
            rest_framework.serializers.ValidationError: If validation fails,
                with specific error message describing the issue.

        Checks:
        - Total points spent <= budget
        - Specializations only where parent >= threshold
        - No values exceed CG max
        """
        from world.skills.models import SkillPointBudget, Specialization  # noqa: PLC0415

        budget = SkillPointBudget.get_active_budget()
        skills = self.draft_data.get("skills", {})
        specializations = self.draft_data.get("specializations", {})

        # Calculate total points spent
        skill_points = sum(skills.values())
        spec_points = sum(specializations.values())
        total_spent = skill_points + spec_points

        if total_spent > budget.total_points:
            msg = f"Total skill points ({total_spent}) exceeds budget ({budget.total_points})."
            raise serializers.ValidationError(msg)

        # Validate no skill values exceed CG max
        for value in skills.values():
            if value > budget.max_skill_value:
                msg = f"Skill value ({value}) exceeds maximum allowed ({budget.max_skill_value})."
                raise serializers.ValidationError(msg)

        # Validate no specialization values exceed CG max
        for value in specializations.values():
            if value > budget.max_specialization_value:
                msg = (
                    f"Specialization value ({value}) exceeds maximum allowed "
                    f"({budget.max_specialization_value})."
                )
                raise serializers.ValidationError(msg)

        # Validate specializations have parent at threshold
        for spec_id, spec_value in specializations.items():
            if spec_value > 0:
                try:
                    spec = Specialization.objects.get(pk=int(spec_id))
                    parent_value = skills.get(str(spec.parent_skill_id), 0)
                    if parent_value < budget.specialization_unlock_threshold:
                        msg = (
                            f"Specialization '{spec.name}' requires parent skill "
                            f"at {budget.specialization_unlock_threshold} or higher "
                            f"(current: {parent_value})."
                        )
                        raise serializers.ValidationError(msg)
                except Specialization.DoesNotExist:
                    msg = f"Invalid specialization ID: {spec_id}."
                    raise serializers.ValidationError(msg) from None

    def _is_traits_complete(self) -> bool:
        """
        Check if traits stage is complete.

        Validation rules:
        - CG points must be exactly 0 (all points spent, none remaining)

        Returns:
            True if traits stage is complete, False otherwise
        """
        return self.calculate_cg_points_remaining() == 0

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
