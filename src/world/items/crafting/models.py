"""Models for the crafting submodule.

All models set ``Meta.app_label = "items"`` so Django registers them under the
existing ``items`` app (no new Django app needed). Migrations are deferred to
Task 7 of the crafting framework PR.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models
from django.db.models import Q
from django.utils.functional import cached_property
from evennia.utils.idmapper.models import SharedMemoryModel

from world.items.crafting.constants import CostConsumption, CraftingRecipeKind
from world.room_features.models import RoomFeatureInstance

if TYPE_CHECKING:
    from world.items.models import QualityTier

# Cross-app FK strings — centralised to avoid duplicated-literal smell.
_CHECK_TYPE_FK = "checks.CheckType"
_TRAIT_FK = "traits.Trait"
_QUALITY_TIER_FK = "items.QualityTier"
_ITEM_TEMPLATE_FK = "items.ItemTemplate"
_CONSEQUENCE_FK = "checks.Consequence"


class CraftingRecipe(SharedMemoryModel):
    """Top-level recipe that drives a crafting workflow.

    Each recipe kind is unique (one recipe per kind for now) and carries the
    check configuration, resource costs, and default consumption policy for
    crafting attempts.
    """

    name = models.CharField(max_length=200, unique=True)
    kind = models.CharField(
        max_length=40,
        choices=CraftingRecipeKind.choices,
        help_text="Determines which crafting flow this recipe drives.",
    )
    check_type = models.ForeignKey(
        _CHECK_TYPE_FK,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Check rolled when attempting this recipe. Unset = recipe disabled.",
    )
    base_difficulty = models.PositiveIntegerField(
        default=0,
        help_text="Base target difficulty passed to perform_check.",
    )
    success_level_step = models.PositiveIntegerField(
        default=10,
        help_text="Quality-score points added per success_level above min_success_level.",
    )
    min_success_level = models.IntegerField(
        default=1,
        help_text="Success levels below this threshold → attempt fails, no output produced.",
    )
    skill_trait = models.ForeignKey(
        _TRAIT_FK,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Trait (skill) whose rank gates or boosts this recipe. Optional.",
    )
    action_point_cost = models.PositiveIntegerField(
        default=0,
        help_text="Action points spent when initiating a crafting attempt.",
    )
    anima_cost = models.PositiveIntegerField(
        default=0,
        help_text="Anima spent when initiating a crafting attempt.",
    )
    default_cost_consumption = models.CharField(
        max_length=20,
        choices=CostConsumption.choices,
        default=CostConsumption.FULL,
        help_text="How ingredient items are consumed by default on resolution.",
    )
    requires_station = models.BooleanField(
        default=True,
        help_text=(
            "Whether this recipe requires an active, undamaged LAB station in the "
            "crafter's room. Default True; future non-physical crafting kinds may "
            "opt out without a schema change."
        ),
    )
    output_item_template = models.ForeignKey(
        "items.ItemTemplate",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "For ITEM_CREATE: the template this recipe produces. Null for attach "
            "kinds (FACET_ATTACH / STYLE_ATTACH)."
        ),
    )
    requires_knowledge = models.BooleanField(
        default=False,
        help_text=(
            "When True, only a character who holds CharacterRecipeKnowledge for this "
            "recipe may browse or craft it (#2242) — a taught/discovered pattern. "
            "Default False: an open recipe anyone with the skill can make."
        ),
    )

    class Meta:
        app_label = "items"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "output_item_template"],
                name="items_craftingrecipe_kind_output_unique",
            ),
        ]

    def __str__(self) -> str:
        return self.name  # noqa: STRING_LITERAL — model display, not an identifier

    @cached_property
    def cached_modifier_outcomes(self) -> list[CraftingRecipeModifier]:
        """Modifier outcomes for this recipe, loaded once and cached."""
        return list(self.modifier_outcomes.all().select_related("target"))


class CraftingMaterialRequirement(SharedMemoryModel):
    """An ingredient required to attempt a crafting recipe.

    Each row declares one item template (and optional minimum quality) that must
    be present in the crafter's inventory when initiating a crafting attempt.
    """

    recipe = models.ForeignKey(
        CraftingRecipe,
        on_delete=models.CASCADE,
        related_name="material_requirements",
    )
    item_template = models.ForeignKey(
        _ITEM_TEMPLATE_FK,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="A specific ingredient template. Mutually exclusive with material_category.",
    )
    material_category = models.ForeignKey(
        "items.MaterialCategory",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "Any template in this category satisfies the requirement. Mutually "
            "exclusive with item_template."
        ),
    )
    quantity = models.PositiveIntegerField(
        default=1,
        help_text="Number of items required.",
    )
    min_quality_tier = models.ForeignKey(
        _QUALITY_TIER_FK,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Minimum quality tier required for the ingredient. Null = any tier.",
    )
    required_value = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Bulk mode (Build 0b): value drawn from the crafter's common-gem bucket for "
            "this material_category tier, instead of counting instances. Only valid with "
            "material_category; when set, quantity is ignored."
        ),
    )

    class Meta:
        app_label = "items"
        constraints = [
            models.CheckConstraint(
                check=(
                    Q(item_template__isnull=False, material_category__isnull=True)
                    | Q(item_template__isnull=True, material_category__isnull=False)
                ),
                name="items_craftingmaterialrequirement_template_xor_category",
            ),
            # required_value (bulk mode) only pairs with a material_category, never a template.
            models.CheckConstraint(
                check=Q(required_value__isnull=True) | Q(material_category__isnull=False),
                name="items_craftingmaterialrequirement_value_needs_category",
            ),
        ]

    def __str__(self) -> str:
        target = self.item_template if self.item_template_id else self.material_category
        if self.required_value is not None:
            return f"{self.required_value} value of {target} for {self.recipe}"
        return f"{self.quantity}x {target} for {self.recipe}"


class CraftingSkillCap(SharedMemoryModel):
    """Maps a minimum skill value to the maximum quality tier craftable.

    Rows are ordered by ``min_skill_value``; the classmethod ``for_skill`` returns
    the max_quality_tier of the highest row whose threshold the crafter meets.
    """

    recipe = models.ForeignKey(
        CraftingRecipe,
        on_delete=models.CASCADE,
        related_name="skill_caps",
    )
    min_skill_value = models.IntegerField(
        help_text="Minimum skill rank required to reach this quality cap.",
    )
    max_quality_tier = models.ForeignKey(
        _QUALITY_TIER_FK,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Highest quality tier achievable at this skill band.",
    )

    class Meta:
        app_label = "items"
        ordering = ["min_skill_value"]
        constraints = [
            models.UniqueConstraint(
                fields=["recipe", "min_skill_value"],
                name="items_craftingskillcap_recipe_min_skill_unique",
            )
        ]

    def __str__(self) -> str:
        return f"{self.recipe}: skill>={self.min_skill_value} → {self.max_quality_tier}"

    @classmethod
    def for_skill(cls, recipe: CraftingRecipe, skill_value: int) -> QualityTier | None:
        """Return the max_quality_tier for the highest skill cap band the crafter qualifies for.

        Finds the row with the largest ``min_skill_value`` that is still <= ``skill_value``
        and returns its ``max_quality_tier``. Returns ``None`` when no rows exist for the
        recipe or when the crafter's skill is below every band's threshold.
        """
        row = (
            cls.objects.filter(recipe=recipe, min_skill_value__lte=skill_value)
            .order_by("-min_skill_value")
            .select_related("max_quality_tier")
            .first()
        )
        if row is None:
            return None
        return row.max_quality_tier


class CraftingRecipeConsequence(SharedMemoryModel):
    """A weighted consequence pool entry for a crafting recipe.

    Pulls from the generic ``checks.Consequence`` model; optionally overrides
    the consequence weight and declares how ingredient costs are consumed if
    this consequence fires.
    """

    recipe = models.ForeignKey(
        CraftingRecipe,
        on_delete=models.CASCADE,
        related_name="consequence_rows",
    )
    consequence = models.ForeignKey(
        _CONSEQUENCE_FK,
        on_delete=models.PROTECT,
        related_name="+",
    )
    weight_override = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Overrides the consequence's default weight in this recipe's pool.",
    )
    cost_consumption = models.CharField(
        max_length=20,
        choices=CostConsumption.choices,
        default=CostConsumption.FULL,
        help_text="How ingredient costs are consumed when this consequence fires.",
    )

    class Meta:
        app_label = "items"
        constraints = [
            models.UniqueConstraint(
                fields=["recipe", "consequence"],
                name="items_craftingrecipeconsequence_recipe_consequence_unique",
            )
        ]

    def __str__(self) -> str:
        return f"{self.recipe}: {self.consequence}"


class CraftingRecipeModifier(SharedMemoryModel):
    """A modifier outcome a crafting recipe grants on the output item.

    Designers author (recipe, target, base_value, quality_scale_factor) rows.
    On successful craft, the service records a CraftedItemRecipe join row.
    At read time, the value is computed:
        final_value = base_value + round(quality_scale_factor * quality_tier.stat_multiplier)
    """

    recipe = models.ForeignKey(
        CraftingRecipe,
        on_delete=models.CASCADE,
        related_name="modifier_outcomes",
    )
    target = models.ForeignKey(
        "mechanics.ModifierTarget",
        on_delete=models.CASCADE,
        related_name="+",
    )
    base_value = models.IntegerField(
        help_text="Flat value granted regardless of quality (can be negative).",
    )
    quality_scale_factor = models.IntegerField(
        default=0,
        help_text="Additional value scaled by the resolved QualityTier.stat_multiplier.",
    )

    class Meta:
        app_label = "items"
        constraints = [
            models.UniqueConstraint(
                fields=["recipe", "target"],
                name="items_craftingrecipemodifier_recipe_target_unique",
            )
        ]

    def __str__(self) -> str:
        sign = "+" if self.base_value >= 0 else ""
        return f"{self.recipe.name}: {sign}{self.base_value} to {self.target.name}"


class CraftedItemRecipe(SharedMemoryModel):
    """Join: a crafting recipe applied to an item instance at a specific quality.

    The quality_tier is the resolved crafting outcome quality (snapshotted at
    craft time). Modifier values are computed at read time from the recipe's
    modifier outcomes × this quality tier.
    """

    item_instance = models.ForeignKey(
        "items.ItemInstance",
        on_delete=models.CASCADE,
        related_name="crafted_recipes",
    )
    recipe = models.ForeignKey(
        CraftingRecipe,
        on_delete=models.CASCADE,
        related_name="crafted_items",
    )
    quality_tier = models.ForeignKey(
        "items.QualityTier",
        on_delete=models.PROTECT,
        related_name="crafted_item_recipes",
        help_text="Quality tier resolved at craft time, used to scale modifier outcomes.",
    )

    class Meta:
        app_label = "items"
        constraints = [
            models.UniqueConstraint(
                fields=["item_instance", "recipe"],
                name="items_crafteditemrecipe_unique",
            )
        ]

    def __str__(self) -> str:
        return f"{self.item_instance} ← {self.recipe.name} ({self.quality_tier.name})"


class LabStationDetails(SharedMemoryModel):
    """Per-Lab durability state — the crafting-station economy (#1234).

    OneToOne to RoomFeatureInstance (mirrors SanctumDetails' shape). Durability
    wears by 1 on every crafting attempt that reaches the roll; a broken (durability
    0) or missing station blocks crafting outright. Repaired via
    ``repair_station_durability`` (world/items/crafting/station.py), a coppers-only
    sink through ``currency.services.transfer``.
    """

    feature_instance = models.OneToOneField(
        RoomFeatureInstance,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="lab_station_details",
    )
    durability = models.PositiveIntegerField(
        help_text="Current wear-remaining before the station is broken.",
    )
    max_durability = models.PositiveIntegerField(
        help_text="Durability ceiling for this station's current level.",
    )

    class Meta:
        app_label = "items"

    def __str__(self) -> str:
        room_id = self.feature_instance.room_profile_id
        return f"Lab station @ room {room_id}: {self.durability}/{self.max_durability}"

    @property
    def is_broken(self) -> bool:
        return self.durability <= 0


class CharacterRecipeKnowledge(SharedMemoryModel):
    """A recipe a character has learned — taught, discovered, or granted (#2242).

    Gates the ``requires_knowledge`` recipes: a character may only browse/craft a
    gated recipe if they hold one of these rows. Open recipes (the default) need
    no row. The acquisition seams are ``teach_recipe`` (an information economy —
    who knows the alaricite pattern) and ``grant_recipe_knowledge`` (GM / future
    discovery via the clue loop).
    """

    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="recipe_knowledge",
    )
    recipe = models.ForeignKey(
        CraftingRecipe,
        on_delete=models.CASCADE,
        related_name="known_by",
    )
    learned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "items"
        ordering = ["character_sheet", "recipe"]
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet", "recipe"],
                name="items_characterrecipeknowledge_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"sheet {self.character_sheet_id} knows {self.recipe}"
