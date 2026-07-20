"""
Unlock models for the progression system.

This module contains models related to unlocks and requirements:
- XP cost system: XPCostChart, XPCostEntry, ClassXPCost, TraitXPCost
- Unlock types: ClassLevelUnlock, TraitRatingUnlock, EliteClassUnlock
- Requirements: AbstractRequirement and all concrete requirement types
- Character unlocks: CharacterUnlock
"""

from typing import ClassVar, cast

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper.models import SharedMemoryModel

from world.traits.models import CharacterTraitValue

# XP Cost System

# Cost modifier constants
NORMAL_COST_PERCENTAGE = 100

# Rating validation constants
RATING_DIVISOR = 10

# Tier calculation constants
TIER_ONE_MAX_LEVEL = 5


class XPCostChart(SharedMemoryModel):
    """
    XP cost charts that apply to multiple classes/traits.

    Instead of having individual cost entries per class/level, we have charts
    that define the cost curve and then apply them to many classes/traits.
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Name for this cost chart",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of when to use this chart",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this chart is active",
    )

    def get_cost_for_level(self, level: int) -> int:
        """Get the XP cost for a specific level from this chart."""
        try:
            cost_entry = self.cost_entries.get(level=level)
            return cost_entry.xp_cost
        except XPCostEntry.DoesNotExist:
            return 0  # No cost defined

    def __str__(self) -> str:
        return self.name

    class Meta:
        ordering: ClassVar[list[str]] = ["name"]


class XPCostEntry(SharedMemoryModel):
    """Individual level/cost entries within an XP cost chart."""

    chart = models.ForeignKey(
        XPCostChart,
        on_delete=models.CASCADE,
        related_name="cost_entries",
    )
    level = models.PositiveIntegerField(
        help_text="Level (for classes) or rating threshold (for traits)",
    )
    xp_cost = models.PositiveIntegerField(help_text="XP cost for this level/rating")

    class Meta:
        unique_together: ClassVar[list[str]] = ["chart", "level"]
        ordering: ClassVar[list[str]] = ["chart", "level"]

    def __str__(self) -> str:
        return f"{self.chart.name} Level {self.level}: {self.xp_cost} XP"


class ClassXPCost(SharedMemoryModel):
    """
    Links classes to XP cost charts with optional modifiers.

    This allows most classes to use standard cost charts, but some elite classes
    can have cost modifiers (e.g., 1.5x more expensive).
    """

    character_class = models.ForeignKey(
        "classes.CharacterClass",
        on_delete=models.CASCADE,
        related_name="xp_costs",
    )
    cost_chart = models.ForeignKey(
        XPCostChart,
        on_delete=models.CASCADE,
        related_name="class_costs",
    )
    cost_modifier = models.PositiveIntegerField(
        default=NORMAL_COST_PERCENTAGE,
        help_text="Cost modifier as percentage (100 = normal, "
        "150 = 50% more expensive, 80 = 20% cheaper)",
    )

    def get_cost_for_level(self, level: int) -> int:
        """Get the modified XP cost for this class at a specific level."""
        base_cost = self.cost_chart.get_cost_for_level(level)
        return int(base_cost * self.cost_modifier / NORMAL_COST_PERCENTAGE)

    class Meta:
        unique_together: ClassVar[list[str]] = ["character_class", "cost_chart"]

    def __str__(self) -> str:
        modifier_str = (
            f" ({self.cost_modifier}%)" if self.cost_modifier != NORMAL_COST_PERCENTAGE else ""
        )
        return f"{self.character_class.name}: {self.cost_chart.name}{modifier_str}"


class TraitXPCost(SharedMemoryModel):
    """
    Links traits to XP cost charts with optional modifiers.

    Similar to ClassXPCost but for trait rating thresholds.
    """

    trait = models.ForeignKey(
        "traits.Trait",
        on_delete=models.CASCADE,
        related_name="xp_costs",
    )
    cost_chart = models.ForeignKey(
        XPCostChart,
        on_delete=models.CASCADE,
        related_name="trait_costs",
    )
    cost_modifier = models.PositiveIntegerField(
        default=NORMAL_COST_PERCENTAGE,
        help_text="Cost modifier as percentage (100 = normal, "
        "150 = 50% more expensive, 80 = 20% cheaper)",
    )

    def get_cost_for_rating(self, rating: int) -> int:
        """Get the modified XP cost for this trait at a specific rating."""
        base_cost = self.cost_chart.get_cost_for_level(rating)
        return int(base_cost * self.cost_modifier / NORMAL_COST_PERCENTAGE)

    class Meta:
        unique_together: ClassVar[list[str]] = ["trait", "cost_chart"]

    def __str__(self) -> str:
        modifier_str = (
            f" ({self.cost_modifier}%)" if self.cost_modifier != NORMAL_COST_PERCENTAGE else ""
        )
        return f"{self.trait.name}: {self.cost_chart.name}{modifier_str}"


# Unlock Types


class ClassLevelUnlock(SharedMemoryModel):
    """Unlocking a new level in a character class."""

    character_class = models.ForeignKey(
        "classes.CharacterClass",
        on_delete=models.CASCADE,
        related_name="level_unlocks",
    )
    target_level = models.PositiveIntegerField(help_text="Level being unlocked")

    def get_xp_cost_for_character(self, character: ObjectDB) -> int:  # noqa: ARG002
        """Get the XP cost for this unlock for a specific character."""
        try:
            class_xp_cost = ClassXPCost.objects.get(
                character_class=self.character_class,
            )
            return class_xp_cost.get_cost_for_level(self.target_level)
        except ClassXPCost.DoesNotExist:
            return 0  # No cost defined

    class Meta:
        unique_together: ClassVar[list[str]] = ["character_class", "target_level"]
        ordering: ClassVar[list[str]] = ["character_class", "target_level"]

    def __str__(self) -> str:
        return f"{self.character_class.name} Level {self.target_level}"


class TraitRatingUnlock(SharedMemoryModel):
    """Unlocking a major trait rating threshold."""

    trait = models.ForeignKey(
        "traits.Trait",
        on_delete=models.CASCADE,
        related_name="rating_unlocks",
    )
    target_rating = models.PositiveIntegerField(
        help_text="Rating being unlocked (should be divisible by 10)",
    )

    def get_xp_cost_for_character(self, character: ObjectDB) -> int:  # noqa: ARG002
        """Get the XP cost for this unlock for a specific character."""
        try:
            trait_xp_cost = TraitXPCost.objects.get(trait=self.trait)
            return trait_xp_cost.get_cost_for_rating(self.target_rating)
        except TraitXPCost.DoesNotExist:
            return 0  # No cost defined

    def clean(self) -> None:
        """Validate that target_rating is divisible by 10."""
        super().clean()
        if cast(int, self.target_rating) % RATING_DIVISOR != 0:
            msg = "Target rating should be divisible by 10"
            raise ValidationError(msg)

    class Meta:
        unique_together: ClassVar[list[str]] = ["trait", "target_rating"]
        ordering: ClassVar[list[str]] = ["trait", "target_rating"]

    def __str__(self) -> str:
        rating = cast(int, self.target_rating)
        return f"{self.trait.name} Rating {rating / RATING_DIVISOR:.1f}"


# Abstract Requirements System


class AbstractUnlockRequirement(models.Model):
    """Abstract base for all types of requirements for unlock targets.

    Generalized from the former ``AbstractClassLevelRequirement`` (#1885):
    the base now supports a polymorphic unlock target — either a
    ``ClassLevelUnlock`` (Durance path), a ``ThreadCrossingThreshold``
    (thread crossing gate), or a ``Path`` (hybrid path entry gate, #2538).
    Exactly one of the three FKs must be set, enforced by a CheckConstraint.

    See ADR-0090 for the boundary choice and the ADR-0016 (shared base) vs
    ADR-0089 (sibling-per-domain) justification.
    """

    description = models.TextField(
        blank=True,
        help_text="Description of this requirement",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this requirement is active",
    )

    # Polymorphic unlock target — exactly one must be set (CheckConstraint below).
    class_level_unlock = models.ForeignKey(
        "ClassLevelUnlock",
        on_delete=models.CASCADE,
        related_name="%(class)s_requirements",
        null=True,
        blank=True,
    )
    thread_crossing_threshold = models.ForeignKey(
        "magic.ThreadCrossingThreshold",
        on_delete=models.CASCADE,
        related_name="%(class)s_requirements",
        null=True,
        blank=True,
        help_text=(
            "Thread crossing threshold this requirement gates. "
            "Exactly one of class_level_unlock / thread_crossing_threshold / path must be set."
        ),
    )
    path = models.ForeignKey(
        "classes.Path",
        on_delete=models.CASCADE,
        related_name="%(class)s_requirements",
        null=True,
        blank=True,
        help_text=(
            "Path this requirement gates (#2538). Used for hybrid path entry "
            "and cross-path technique learning. Exactly one of "
            "class_level_unlock / thread_crossing_threshold / path must be set."
        ),
    )

    class Meta:
        abstract = True
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(class_level_unlock__isnull=False)
                    & models.Q(thread_crossing_threshold__isnull=True)
                    & models.Q(path__isnull=True)
                )
                | (
                    models.Q(class_level_unlock__isnull=True)
                    & models.Q(thread_crossing_threshold__isnull=False)
                    & models.Q(path__isnull=True)
                )
                | (
                    models.Q(class_level_unlock__isnull=True)
                    & models.Q(thread_crossing_threshold__isnull=True)
                    & models.Q(path__isnull=False)
                ),
                name="%(class)s_exactly_one_unlock_target",
            ),
        ]

    def is_met_by_character(self, character: ObjectDB) -> tuple[bool, str]:
        """Check if this requirement is met by the given character."""
        msg = "Subclasses must implement is_met_by_character"
        raise NotImplementedError(msg)


# Backwards-compat alias for any external references to the old name.
AbstractClassLevelRequirement = AbstractUnlockRequirement


class TraitRequirement(AbstractClassLevelRequirement):
    """Requirement for a specific trait at a minimum value."""

    trait = models.ForeignKey(
        "traits.Trait",
        on_delete=models.CASCADE,
        related_name="trait_requirements",
    )
    minimum_value = models.PositiveIntegerField(
        help_text="Minimum trait value required",
    )

    def is_met_by_character(self, character: ObjectDB) -> tuple[bool, str]:
        """Check if character has the required trait value."""
        try:
            trait_value = CharacterTraitValue.objects.get(
                character=character,
                trait=self.trait,
            )
            if trait_value.value >= cast(int, self.minimum_value):
                return (
                    True,
                    f"Has {self.trait.name} {trait_value.display_value}",
                )
            return (
                False,
                f"Need {self.trait.name} {cast(int, self.minimum_value) / RATING_DIVISOR:.1f}, "
                f"have {trait_value.display_value}",
            )
        except ObjectDoesNotExist:
            return (
                False,
                (
                    f"Need {self.trait.name} "
                    f"{cast(int, self.minimum_value) / RATING_DIVISOR:.1f}, trait not set"
                ),
            )

    def __str__(self) -> str:
        minimum_value = cast(int, self.minimum_value)
        return f"Trait: {self.trait.name} >= {minimum_value / RATING_DIVISOR:.1f}"


class LevelRequirement(AbstractClassLevelRequirement):
    """Requirement for a minimum character level."""

    minimum_level = models.PositiveIntegerField(
        help_text="Minimum character level required",
    )

    def is_met_by_character(self, character: ObjectDB) -> tuple[bool, str]:
        """Check if character meets the level requirement."""
        character_levels = character.character_class_levels.all()
        if not character_levels.exists():
            return False, "Character has no class levels"

        highest_level = max(ccl.level for ccl in character_levels)
        if highest_level >= self.minimum_level:
            return True, f"Character is level {highest_level}"
        return (
            False,
            f"Need level {self.minimum_level}, character is {highest_level}",
        )

    def __str__(self) -> str:
        return f"Level: >= {self.minimum_level}"


class ClassLevelRequirement(AbstractClassLevelRequirement):
    """Requirement for a specific level in a specific class."""

    character_class = models.ForeignKey(
        "classes.CharacterClass",
        on_delete=models.CASCADE,
    )
    minimum_level = models.PositiveIntegerField(
        help_text="Minimum level required in this class",
    )

    def is_met_by_character(self, character: ObjectDB) -> tuple[bool, str]:
        """Check if character has the required level in the specific class."""
        try:
            class_level = character.character_class_levels.get(
                character_class=self.character_class,
            )
            if class_level.level >= self.minimum_level:
                return (
                    True,
                    f"Has {self.character_class.name} level {class_level.level}",
                )
            return (
                False,
                f"Need {self.character_class.name} level {self.minimum_level}, "
                f"have {class_level.level}",
            )
        except ObjectDoesNotExist:
            return (
                False,
                f"Need {self.character_class.name} level {self.minimum_level}, don't have class",
            )

    def __str__(self) -> str:
        return f"Class Level: {self.character_class.name} >= {self.minimum_level}"


class MultiClassRequirement(AbstractClassLevelRequirement):
    """Requirement for having multiple classes at specific levels."""

    required_classes = models.ManyToManyField(
        "classes.CharacterClass",
        through="MultiClassLevel",
        related_name="multi_requirements",
    )
    description_override = models.CharField(
        max_length=255,
        blank=True,
        help_text="Override description (e.g., 'Two different classes at level 6+')",
    )

    def is_met_by_character(self, character: ObjectDB) -> tuple[bool, str]:
        """Check if character meets the multi-class requirements."""
        character_levels = {
            ccl.character_class: ccl.level for ccl in character.character_class_levels.all()
        }

        met_requirements = 0
        required_count = self.class_levels.count()

        for mcl in self.class_levels.all():
            if character_levels.get(mcl.character_class, 0) >= mcl.minimum_level:
                met_requirements += 1

        if met_requirements >= required_count:
            return (
                True,
                f"Has {met_requirements}/{required_count} required class levels",
            )
        return (
            False,
            f"Need {required_count} class requirements, have {met_requirements}",
        )

    def __str__(self) -> str:
        if self.description_override:
            return self.description_override
        return f"Multi-class requirement with {self.class_levels.count()} classes"


class MultiClassLevel(SharedMemoryModel):
    """Through model for multi-class requirements."""

    multi_class_requirement = models.ForeignKey(
        MultiClassRequirement,
        on_delete=models.CASCADE,
        related_name="class_levels",
    )
    character_class = models.ForeignKey(
        "classes.CharacterClass",
        on_delete=models.CASCADE,
    )
    minimum_level = models.PositiveIntegerField(
        help_text="Minimum level required in this class",
    )

    class Meta:
        unique_together: ClassVar[list[str]] = [
            "multi_class_requirement",
            "character_class",
        ]


class AchievementRequirement(AbstractClassLevelRequirement):
    """Requirement based on character achievements."""

    achievement = models.ForeignKey(
        "achievements.Achievement",
        on_delete=models.CASCADE,
        help_text="The achievement required",
    )

    def is_met_by_character(self, character: ObjectDB) -> tuple[bool, str]:
        """Check if character has the required achievement."""
        from world.achievements.models import (  # noqa: PLC0415
            CharacterAchievement,
        )

        has_it = CharacterAchievement.objects.filter(
            character_sheet=character.sheet_data,
            achievement=self.achievement,
        ).exists()
        if has_it:
            return True, f"Has achievement: {self.achievement.name}"
        return False, f"Missing achievement: {self.achievement.name}"

    def __str__(self) -> str:
        return f"Achievement: {self.achievement.name}"


class RelationshipRequirement(AbstractClassLevelRequirement):
    """Requirement based on the character's own relationship-track progress.

    Character-intrinsic like every sibling requirement (#2116): counts the
    character's own ``RelationshipTrackProgress`` rows (as the relationship's
    ``source``) that have reached ``minimum_tier`` on a track, optionally
    narrowed to one ``required_track_kind``. Met when at least
    ``minimum_count`` such tracks qualify. Replaces the former freeform
    ``relationship_target``/``minimum_level`` shape — a specific-named-person
    gate was rejected (target resolution by name is ambiguous/renameable and
    no sibling requirement is other-character-shaped; deferred as a
    needs-design follow-up if content design wants it later).
    """

    required_track_kind = models.ForeignKey(
        "relationships.RelationshipTrack",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Track this requirement gates. Null = any track qualifies.",
    )
    minimum_tier = models.PositiveIntegerField(
        help_text="Minimum RelationshipTier.tier_number the track must have reached.",
    )
    minimum_count = models.PositiveSmallIntegerField(
        default=1,
        help_text="Number of qualifying tracks required (at/above minimum_tier).",
    )

    def is_met_by_character(self, character: ObjectDB) -> tuple[bool, str]:
        """Count the character's own qualifying relationship tracks.

        Unmet text renders only the authored gate + the character's own progress —
        never another party's relationship data (#2116 leak-analysis contract).
        """
        from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
        from world.relationships.models import RelationshipTrackProgress  # noqa: PLC0415

        try:
            sheet = character.sheet_data
        except (CharacterSheet.DoesNotExist, AttributeError):
            return False, f"{self._gate_description()}, have 0"

        qs = RelationshipTrackProgress.objects.filter(
            relationship__source=sheet,
            relationship__is_active=True,
        ).select_related("track")
        if self.required_track_kind_id is not None:
            qs = qs.filter(track=self.required_track_kind_id)

        count = 0
        for progress in qs:
            qualifying_tiers = [
                tier
                for tier in progress.track.cached_tiers
                if tier.point_threshold <= progress.developed_points
            ]
            if not qualifying_tiers:
                continue
            highest_tier_number = max(tier.tier_number for tier in qualifying_tiers)
            if highest_tier_number >= self.minimum_tier:
                count += 1

        if count >= self.minimum_count:
            return True, f"{self._gate_description()}, have {count}"
        return False, f"{self._gate_description()}, have {count}"

    def _gate_description(self) -> str:
        """Authored-gate text only — never names another character's tracks."""
        track_clause = (
            f"on {self.required_track_kind.name}" if self.required_track_kind_id else "any track"
        )
        return (
            f"Need {self.minimum_count} relationship track(s) {track_clause} "
            f"at tier >= {self.minimum_tier}"
        )

    def __str__(self) -> str:
        track_name = self.required_track_kind.name if self.required_track_kind_id else "Any"
        return f"Relationship: {track_name} tier >= {self.minimum_tier} (x{self.minimum_count})"


class LegendRequirement(AbstractClassLevelRequirement):
    """Requires a minimum total legend value for path leveling."""

    minimum_legend = models.PositiveIntegerField(
        help_text="Minimum total legend required",
    )

    class Meta:
        verbose_name = "Legend Requirement"
        verbose_name_plural = "Legend Requirements"
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(class_level_unlock__isnull=False)
                    & models.Q(thread_crossing_threshold__isnull=True)
                )
                | (
                    models.Q(class_level_unlock__isnull=True)
                    & models.Q(thread_crossing_threshold__isnull=False)
                ),
                name="legendrequirement_exactly_one_unlock_target",
            ),
        ]

    def __str__(self) -> str:
        return f"Legend >= {self.minimum_legend}"

    def is_met_by_character(self, character: ObjectDB) -> tuple[bool, str]:
        from world.societies.services import (  # noqa: PLC0415
            get_character_legend_total,
        )

        total = get_character_legend_total(character)
        if total >= self.minimum_legend:
            return True, f"Legend {total} meets requirement of {self.minimum_legend}"
        return False, f"Legend {total} < {self.minimum_legend} required"


class TierRequirement(AbstractClassLevelRequirement):
    """Requirement for a character to have reached a specific tier in any class."""

    minimum_tier = models.PositiveIntegerField(
        help_text="Minimum tier required (1 for levels 1-5, 2 for levels 6-10)",
    )

    def is_met_by_character(self, character: ObjectDB) -> tuple[bool, str]:
        """Check if character has reached the required tier in any class."""
        character_levels = character.character_class_levels.all()
        if not character_levels.exists():
            return False, "Character has no class levels"

        highest_level = max(ccl.level for ccl in character_levels)
        character_tier = 1 if highest_level <= TIER_ONE_MAX_LEVEL else 2

        if character_tier >= cast(int, self.minimum_tier):
            return True, f"Character is tier {character_tier} (level {highest_level})"
        return (
            False,
            f"Need tier {cast(int, self.minimum_tier)}, character is tier {character_tier}",
        )

    def __str__(self) -> str:
        return f"Tier: >= {cast(int, self.minimum_tier)}"


class ItemRequirement(AbstractClassLevelRequirement):
    """Requirement based on possessing a physical touchstone/trophy item.

    Dual mode, mirroring RitualComponentRequirement's shape (ADR-0087):
    exactly one of item_template (a fixed narrative trophy) or
    min_touchstone_tier (any attuned item tied to a Resonance the character
    holds, at/above a tier floor) is set. Possession-only — is_met_by_character
    never consumes the qualifying item (#1859 Decision 4).
    """

    item_template = models.ForeignKey(
        "items.ItemTemplate",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="class_level_item_requirements",
    )
    min_touchstone_tier = models.ForeignKey(
        "magic.ResonanceTier",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "Touchstone mode: any item attuned to the character, tied to a "
            "Resonance they've claimed, at or above this tier, satisfies this "
            "requirement. Exactly one of item_template/min_touchstone_tier is set."
        ),
    )
    quantity = models.PositiveSmallIntegerField(
        default=1,
        help_text="Template-mode only; touchstone-mode is a possess-at-least-one check.",
    )
    min_quality_tier = models.ForeignKey(
        "items.QualityTier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Template-mode only; ignored in touchstone mode.",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(item_template__isnull=False)
                    & models.Q(min_touchstone_tier__isnull=True)
                )
                | (
                    models.Q(item_template__isnull=True)
                    & models.Q(min_touchstone_tier__isnull=False)
                ),
                name="itemrequirement_exactly_one_mode",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(class_level_unlock__isnull=False)
                    & models.Q(thread_crossing_threshold__isnull=True)
                )
                | (
                    models.Q(class_level_unlock__isnull=True)
                    & models.Q(thread_crossing_threshold__isnull=False)
                ),
                name="itemrequirement_exactly_one_unlock_target",
            ),
        ]

    def is_met_by_character(self, character: ObjectDB) -> tuple[bool, str]:
        """Check possession of a qualifying item. Never consumes it."""
        from world.items.models import ItemInstance  # noqa: PLC0415
        from world.items.services.materials import meets_quality_tier  # noqa: PLC0415

        sheet = character.sheet_data

        if self.item_template_id is not None:
            candidates = (
                ItemInstance.objects.in_play()
                .filter(holder_character_sheet=sheet, template_id=self.item_template_id)
                .select_related("quality_tier")
            )
            total_qty = sum(inst.quantity for inst in candidates if meets_quality_tier(inst, self))
            if total_qty >= self.quantity:
                return True, f"Has {self.quantity}x {self.item_template.name}"
            return (
                False,
                f"Need {self.quantity}x {self.item_template.name}, have {total_qty}",
            )

        from world.magic.models import CharacterResonance  # noqa: PLC0415

        claimed_resonance_ids = set(
            CharacterResonance.objects.filter(character_sheet=sheet).values_list(
                "resonance_id", flat=True
            )
        )
        has_touchstone = (
            ItemInstance.objects.in_play()
            .filter(
                holder_character_sheet=sheet,
                attuned_to_character_sheet=sheet,
                template__tied_resonance_id__in=claimed_resonance_ids,
                template__resonance_tier__tier_level__gte=self.min_touchstone_tier.tier_level,
            )
            .exists()
        )
        if has_touchstone:
            return True, f"Has touchstone (tier >= {self.min_touchstone_tier.name})"
        return (
            False,
            f"Need an attuned touchstone (tier >= {self.min_touchstone_tier.name})",
        )

    def __str__(self) -> str:
        if self.item_template_id is not None:
            return f"Item: {self.quantity}x {self.item_template}"
        return f"Touchstone: tier >= {self.min_touchstone_tier.name}"


class MajorGiftTechniqueRequirement(AbstractClassLevelRequirement):
    """Requirement for knowing >= N techniques of the character's MAJOR gift.

    Level-2 gate (#2440 ruling 4): CG hands out only 1-3 starter picks from
    the (Path x Gift) pool (1 + Tradition Training rank); the design intent
    is that characters fill out the rest of their starter gift in play via
    Academy/Archive TRAIN offers before crossing to level 2. The gate is a
    COUNT, not completeness — a major gift can grow many techniques over a
    character's life (several level-gated), so requiring every technique
    would be a moving, unreachable target. ``minimum_techniques`` defaults
    to 3, matching CG's upper end.

    Only the character's single MAJOR gift counts (``Gift.kind ==
    GiftKind.MAJOR``, resolved via ``CharacterGift`` — CG links exactly
    one). Minor-gift techniques never count toward this gate.
    """

    minimum_techniques = models.PositiveSmallIntegerField(
        default=3,
        help_text="Techniques of the character's MAJOR gift required (#2440 ruling 4).",
    )

    def is_met_by_character(self, character: ObjectDB) -> tuple[bool, str]:
        """Count CharacterTechnique rows whose technique belongs to the MAJOR gift."""
        from world.magic.constants import GiftKind  # noqa: PLC0415
        from world.magic.models import CharacterGift  # noqa: PLC0415
        from world.magic.services.gift_acquisition import (  # noqa: PLC0415
            count_techniques_for_gift,
        )

        sheet = character.sheet_data
        major_link = CharacterGift.objects.filter(
            character=sheet, gift__kind=GiftKind.MAJOR
        ).first()
        if major_link is None:
            return (
                False,
                f"Need {self.minimum_techniques} techniques of your major gift, have no major gift",
            )

        count = count_techniques_for_gift(sheet, major_link.gift)
        if count >= cast(int, self.minimum_techniques):
            return True, f"Knows {count} techniques of {major_link.gift.name}"
        return (
            False,
            f"Need {self.minimum_techniques} techniques of {major_link.gift.name}, have {count}",
        )

    def __str__(self) -> str:
        return f"Major Gift Techniques: >= {self.minimum_techniques}"


# Character Unlocks


class CharacterUnlock(SharedMemoryModel):
    """Records what class levels a character has unlocked."""

    character = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="unlocks",
    )
    character_class = models.ForeignKey(
        "classes.CharacterClass",
        on_delete=models.CASCADE,
        related_name="character_unlocks",
    )
    target_level = models.PositiveIntegerField(
        help_text="Level unlocked for this class",
    )
    unlocked_date = models.DateTimeField(auto_now_add=True)
    xp_spent = models.PositiveIntegerField(
        default=0,
        help_text="XP actually spent on this unlock",
    )

    class Meta:
        unique_together: ClassVar[list[str]] = [
            "character",
            "character_class",
            "target_level",
        ]
        ordering: ClassVar[list[str]] = ["-unlocked_date"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["character", "-unlocked_date"])
        ]

    def __str__(self) -> str:
        return f"{self.character.key}: {self.character_class.name} Level {self.target_level}"
