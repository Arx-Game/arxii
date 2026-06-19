"""Models for the crafting submodule.

All models set ``Meta.app_label = "items"`` so Django registers them under the
existing ``items`` app (no new Django app needed). Migrations are deferred to
Task 7 of the crafting framework PR.
"""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.items.crafting.constants import CostConsumption, CraftingRecipeKind

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
        unique=True,
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

    class Meta:
        app_label = "items"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name  # noqa: STRING_LITERAL — model display, not an identifier


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
        related_name="+",
    )
    quantity = models.PositiveIntegerField(
        default=1,
        help_text="Number of items of this template required.",
    )
    min_quality_tier = models.ForeignKey(
        _QUALITY_TIER_FK,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Minimum quality tier required for the ingredient. Null = any tier.",
    )

    class Meta:
        app_label = "items"

    def __str__(self) -> str:
        return f"{self.quantity}x {self.item_template} for {self.recipe}"


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
    def for_skill(cls, recipe: CraftingRecipe, skill_value: int) -> object | None:
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
