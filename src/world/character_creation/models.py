"""
Character Creation models.

Models for the staged character creation flow:
- StartingArea: Selectable origin locations that gate heritage options
- Beginnings: Worldbuilding paths (e.g., Sleeper, Normal Upbringing) for each area
- CharacterDraft: In-progress character creation state
"""

from __future__ import annotations

from datetime import timedelta

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper.models import SharedMemoryModel
from rest_framework import serializers

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.character_creation.constants import (
    AGE_MAX,
    AGE_MIN,
    REQUIRED_STATS,
    STAT_BASE_POINTS,
    STAT_DEFAULT_VALUE,
    STAT_DISPLAY_DIVISOR,
    STAT_FREE_POINTS,
    STAT_MAX_VALUE,
    STAT_MIN_VALUE,
    ApplicationStatus,
    CommentType,
    Stage,
    StartingAreaAccessLevel,
)
from world.character_creation.types import (
    CGPointBreakdownEntry,
    StageValidationErrors,
    StatAdjustment,
)
from world.classes.models import PathStage


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
    xp_conversion_rate = models.PositiveIntegerField(
        default=2,
        help_text="XP awarded per unspent CG point (e.g., 2 means 2 XP per 1 CG point)",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        verbose_name = "CG Point Budget"
        verbose_name_plural = "CG Point Budgets"

    def __str__(self) -> str:
        active = " (Active)" if self.is_active else ""
        return f"{self.name}: {self.starting_points} points{active}"

    @classmethod
    def get_active_budget(cls) -> int:
        """Get the current active CG point budget."""
        budget = cls.objects.filter(is_active=True).first()
        return budget.starting_points if budget else 100

    @classmethod
    def get_active_conversion_rate(cls) -> int:
        """Get the current active CG point to XP conversion rate."""
        budget = cls.objects.filter(is_active=True).first()
        return budget.xp_conversion_rate if budget else 2


class StartingArea(NaturalKeyMixin, SharedMemoryModel):
    """
    A starting location/city that players can select in character creation.

    Each area gates which heritage options, species, and families are available.
    Maps to an Evennia room for character starting location.

    Note: Rooms may be None during early testing before grid is built.
    """

    # Alias for backward compatibility — canonical definition is in constants.py
    AccessLevel = StartingAreaAccessLevel

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

    def __str__(self) -> str:
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
    # TODO: Implement finalize_character integration to grant society awareness/membership
    # based on this field. See societies system design doc for details.
    societies = models.ManyToManyField(
        "societies.Society",
        blank=True,
        related_name="connected_beginnings",
        help_text="Societies characters gain awareness/membership in during character creation",
    )
    traditions = models.ManyToManyField(
        "magic.Tradition",
        through="BeginningTradition",
        blank=True,
        related_name="available_beginnings",
        help_text="Traditions available for this beginning during CG.",
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
    heritage = models.ForeignKey(
        "character_sheets.Heritage",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="beginnings",
        help_text="Heritage type for characters with this beginning "
        "(e.g., Sleeper, Misbegotten). "
        "Null defaults to 'Normal' heritage at finalization.",
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

    def __str__(self) -> str:
        return f"{self.name} ({self.starting_area.name})"

    def is_accessible_by(self, account: AccountDB) -> bool:
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

    def get_available_species(self) -> models.QuerySet:
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

    def get_starting_languages(self, species: models.Model) -> models.QuerySet:
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


class BeginningTradition(models.Model):
    """Maps which traditions are available for each beginning during CG.
    CG-only concern -- traditions exist independently post-CG."""

    beginning = models.ForeignKey(
        Beginnings,
        on_delete=models.CASCADE,
        related_name="beginning_traditions",
    )
    tradition = models.ForeignKey(
        "magic.Tradition",
        on_delete=models.CASCADE,
        related_name="beginning_traditions",
    )
    required_distinction = models.ForeignKey(
        "distinctions.Distinction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Distinction required to select this tradition for this beginning.",
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display order within this beginning's tradition list.",
    )

    class Meta:
        unique_together = ["beginning", "tradition"]
        ordering = ["sort_order"]
        verbose_name = "Beginning Tradition"
        verbose_name_plural = "Beginning Traditions"

    def __str__(self) -> str:
        return f"{self.beginning} -> {self.tradition}"


class CharacterDraft(models.Model):
    """
    In-progress character creation state.

    Stores all staged data as JSON, allowing players to leave and return
    without losing progress. Drafts expire after 2 months of account inactivity.
    """

    # Stage enum imported from constants.py for easier external access
    Stage = Stage

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
    selected_tradition = models.ForeignKey(
        "magic.Tradition",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Selected magical tradition (gates magic template).",
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

    def __str__(self) -> str:
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

    def get_starting_room(self) -> ObjectDB | None:
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
        Uses get_stage_validation_errors() so both share cached computation.
        """
        errors = self.get_stage_validation_errors()
        return {
            stage: not errors.get(stage, []) for stage in self.Stage if stage != self.Stage.REVIEW
        } | {self.Stage.REVIEW: False}

    def get_stage_validation_errors(self) -> StageValidationErrors:
        """
        Get validation errors for each stage.

        Returns dict mapping stage number to list of error messages.
        Empty list means the stage is complete. Result is cached on the
        instance so get_stage_completion() and serializer share computation.
        """
        if hasattr(self, "_cached_stage_errors"):
            return self._cached_stage_errors

        from world.character_creation.validators import get_all_stage_errors  # noqa: PLC0415

        errors = get_all_stage_errors(self)
        self._cached_stage_errors = errors
        return errors

    def _is_heritage_complete(self) -> bool:
        """Check if heritage stage is complete."""
        return not self.get_stage_validation_errors().get(self.Stage.HERITAGE, [])

    def _is_lineage_complete(self) -> bool:
        """Check if lineage stage is complete."""
        return not self.get_stage_validation_errors().get(self.Stage.LINEAGE, [])

    def _get_distinction_bonus(self, modifier_target_name: str, category_name: str) -> int:
        """Sum distinction effect values targeting a specific ModifierTarget."""
        from world.distinctions.models import DistinctionEffect  # noqa: PLC0415

        distinctions_data = self.draft_data.get("distinctions", [])
        if not distinctions_data:
            return 0

        entries = {
            d["distinction_id"]: d.get("rank", 1)
            for d in distinctions_data
            if d.get("distinction_id")
        }
        if not entries:
            return 0

        effects = DistinctionEffect.objects.filter(
            distinction_id__in=entries.keys(),
            target__name=modifier_target_name,
            target__category__name=category_name,
        ).select_related("target")

        return sum(effect.get_value_at_rank(entries[effect.distinction_id]) for effect in effects)

    def get_stats_max_free_points(self) -> int:
        """Return the total number of free stat points available (base + distinction bonus)."""
        bonus = self._get_distinction_bonus("attribute_free_points", "stat")
        return STAT_FREE_POINTS + bonus

    def calculate_stats_free_points(self) -> int:
        """
        Calculate remaining free points from stat allocations.

        Starting budget:
        - Base: 9 stats × 2 = 18 points
        - Free: 5 points + distinction bonuses
        - Total: base + free + bonuses

        Current spend: sum(stats.values()) / 10
        Remaining: total_budget - spent

        Returns:
            Number of free points remaining (can be negative if over budget)
        """
        max_free = self.get_stats_max_free_points()
        total_budget = STAT_BASE_POINTS + max_free

        stats = self.draft_data.get("stats", {})
        if not stats:
            return max_free

        spent = sum(stats.values()) / STAT_DISPLAY_DIVISOR
        return int(total_budget - spent)

    def calculate_cg_points_breakdown(self) -> list[CGPointBreakdownEntry]:
        """
        Build itemized breakdown of CG point costs from actual data sources.

        Returns:
            List of typed dicts with category, item, and cost keys.
        """
        breakdown: list[CGPointBreakdownEntry] = []
        if self.selected_beginnings and self.selected_beginnings.cg_point_cost:
            breakdown.append(
                {
                    "category": "heritage",
                    "item": self.selected_beginnings.name,
                    "cost": self.selected_beginnings.cg_point_cost,
                }
            )
        for d in self.draft_data.get("distinctions", []):
            cost = d.get("cost", 0)
            if cost:
                breakdown.append(
                    {
                        "category": "distinction",
                        "item": d.get("distinction_name", "Unknown"),
                        "cost": cost,
                    }
                )
        return breakdown

    def calculate_cg_points_spent(self) -> int:
        """
        Calculate total CG points spent from actual data sources.

        Derived from breakdown to guarantee consistency.

        Returns:
            Total CG points spent
        """
        return sum(entry["cost"] for entry in self.calculate_cg_points_breakdown())

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

    def get_stat_bonuses_from_distinctions(self) -> dict[str, int]:
        """Get stat bonuses from selected distinctions.

        Looks up DistinctionEffect records for each selected distinction
        and returns bonuses for effects targeting the 'stat' category.

        Returns:
            Dict mapping stat names to display-scale bonus values
            (e.g., {"strength": 1} for +10 internal).
        """
        from world.distinctions.models import DistinctionEffect  # noqa: PLC0415
        from world.mechanics.constants import STAT_CATEGORY_NAME  # noqa: PLC0415

        distinctions_data = self.draft_data.get("distinctions", [])
        if not distinctions_data:
            return {}

        distinction_ids = [d["distinction_id"] for d in distinctions_data]
        ranks_by_id = {d["distinction_id"]: d.get("rank", 1) for d in distinctions_data}

        effects = (
            DistinctionEffect.objects.filter(
                distinction_id__in=distinction_ids,
                target__category__name=STAT_CATEGORY_NAME,
            )
            .select_related("target", "target__category")
            .distinct()
        )

        bonuses: dict[str, int] = {}
        for effect in effects:
            stat_name = effect.target.name
            rank = ranks_by_id.get(effect.distinction_id, 1)
            value = effect.get_value_at_rank(rank)
            display_value = value // STAT_DISPLAY_DIVISOR
            bonuses[stat_name] = bonuses.get(stat_name, 0) + display_value

        return bonuses

    def get_all_stat_bonuses(self) -> dict[str, int]:
        """Get combined stat bonuses from all sources.

        Aggregates bonuses from heritage (species) and distinctions.

        Returns:
            Dict mapping stat names to total display-scale values.
        """
        heritage = self.get_stat_bonuses_from_heritage()
        distinctions = self.get_stat_bonuses_from_distinctions()

        combined: dict[str, int] = {}
        all_stats = set(heritage.keys()) | set(distinctions.keys())
        for stat in all_stats:
            combined[stat] = heritage.get(stat, 0) + distinctions.get(stat, 0)
        return combined

    def enforce_stat_caps(self) -> list[StatAdjustment]:
        """Enforce stat caps after distinction changes.

        If any allocated stat + bonuses > STAT_MAX_VALUE, reduces
        the allocation and returns a list of adjustments made.
        """
        stats = self.draft_data.get("stats", {})
        if not stats:
            return []

        bonuses = self.get_all_stat_bonuses()
        adjustments: list[StatAdjustment] = []

        for stat_name, allocated in stats.items():
            bonus_display = bonuses.get(stat_name, 0)
            bonus_internal = bonus_display * STAT_DISPLAY_DIVISOR
            if allocated + bonus_internal > STAT_MAX_VALUE:
                old_display = allocated // STAT_DISPLAY_DIVISOR
                new_allocated = STAT_MAX_VALUE - bonus_internal
                new_allocated = max(new_allocated, STAT_MIN_VALUE)
                new_display = new_allocated // STAT_DISPLAY_DIVISOR
                stats[stat_name] = new_allocated
                adjustments.append(
                    StatAdjustment(
                        stat=stat_name,
                        old_display=old_display,
                        new_display=new_display,
                        reason=f"Bonuses provide +{bonus_display}",
                    )
                )

        if adjustments:
            self.draft_data["stats"] = stats
            self.save(update_fields=["draft_data", "updated_at"])

        return adjustments

    def calculate_final_stats(self) -> dict[str, int]:
        """
        Calculate final stat values including all bonuses.

        Final stats = allocated points + all bonuses (converted to
        internal scale). Includes heritage and distinction bonuses.

        Returns:
            Dict mapping stat names to final internal values (10-50+)
        """
        allocated = self.draft_data.get("stats", {})
        bonuses = self.get_all_stat_bonuses()

        final_stats = {}
        for stat_name in REQUIRED_STATS:
            base = allocated.get(stat_name, STAT_DEFAULT_VALUE)
            bonus = bonuses.get(stat_name, 0) * 10  # Convert to internal scale
            final_stats[stat_name] = base + bonus

        return final_stats

    def _is_attributes_complete(self) -> bool:
        """Check if attributes stage is complete."""
        return not self.get_stage_validation_errors().get(self.Stage.ATTRIBUTES, [])

    def _is_path_skills_complete(self) -> bool:
        """Check Stage 5 (Path & Skills) completion status."""
        return not self.get_stage_validation_errors().get(self.Stage.PATH_SKILLS, [])

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

    def _is_distinctions_complete(self) -> bool:
        """Check if distinctions stage is complete."""
        return not self.get_stage_validation_errors().get(self.Stage.DISTINCTIONS, [])

    def _is_appearance_complete(self) -> bool:
        """Check if appearance stage is complete."""
        return not self.get_stage_validation_errors().get(self.Stage.APPEARANCE, [])

    def _is_identity_complete(self) -> bool:
        """Check if identity stage is complete."""
        return not self.get_stage_validation_errors().get(self.Stage.IDENTITY, [])

    def can_submit(self) -> bool:
        """Check if all required stages are complete for submission."""
        completion = self.get_stage_completion()
        # All stages except REVIEW must be complete
        required_stages = [s for s in self.Stage if s != self.Stage.REVIEW]
        return all(completion.get(stage, False) for stage in required_stages)


SOFT_DELETE_DAYS = 14


class DraftApplication(models.Model):
    """Tracks the review lifecycle of a character draft submission."""

    draft = models.OneToOneField(
        CharacterDraft,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="application",
    )
    player_account = models.ForeignKey(
        AccountDB,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_applications",
        help_text="The player who submitted this application (survives draft deletion).",
    )
    character_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Character name populated at approval time (survives draft deletion).",
    )
    status = models.CharField(
        max_length=30,
        choices=ApplicationStatus.choices,
        default=ApplicationStatus.SUBMITTED,
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewer = models.ForeignKey(
        AccountDB,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="claimed_applications",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    submission_notes = models.TextField(
        blank=True,
        help_text="Player's notes about the character submission.",
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set on deny/withdraw for soft-delete grace period.",
    )

    class Meta:
        verbose_name = "Draft Application"
        verbose_name_plural = "Draft Applications"

    def __str__(self) -> str:
        name = self.draft or self.character_name or "Unknown"
        return f"Application for {name} ({self.get_status_display()})"

    @property
    def is_locked(self) -> bool:
        """Draft is locked (read-only for player) when submitted or in review."""
        return self.status in (ApplicationStatus.SUBMITTED, ApplicationStatus.IN_REVIEW)

    @property
    def is_terminal(self) -> bool:
        """Application is in a terminal state (approved, denied, withdrawn)."""
        return self.status in (
            ApplicationStatus.APPROVED,
            ApplicationStatus.DENIED,
            ApplicationStatus.WITHDRAWN,
        )

    @property
    def is_editable(self) -> bool:
        """Draft is editable when revisions are requested."""
        return self.status == ApplicationStatus.REVISIONS_REQUESTED


class DraftApplicationComment(models.Model):
    """A comment or status change event in an application's conversation thread."""

    application = models.ForeignKey(
        DraftApplication,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    author = models.ForeignKey(
        AccountDB,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Null for system-generated status change events.",
    )
    text = models.TextField()
    comment_type = models.CharField(
        max_length=20,
        choices=CommentType.choices,
        default=CommentType.MESSAGE,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Application Comment"
        verbose_name_plural = "Application Comments"
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.get_comment_type_display()} on {self.application} at {self.created_at}"


class CGExplanation(SharedMemoryModel):
    """Key-value store for admin-editable CG explanatory text.

    Each row is one piece of CG copy (heading, intro, description, etc.).
    The key matches what the frontend expects (e.g. "origin_heading").
    Staff can add new keys directly in the admin without migrations.
    """

    key = models.CharField(max_length=100, unique=True)
    text = models.TextField(blank=True)
    help_text = models.TextField(blank=True, help_text="Reminder of which CG stage uses this key")

    class Meta:
        verbose_name = "CG Explanation"
        verbose_name_plural = "CG Explanations"

    def __str__(self) -> str:
        return self.key
