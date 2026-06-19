"""Models for the crafting submodule.

All models set ``Meta.app_label = "items"`` so Django registers them under the
existing ``items`` app (no new Django app needed). Migrations are deferred to
Task 7 of the crafting framework PR.
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.items.crafting.constants import CostConsumption, CraftingRecipeKind

# Cross-app FK strings — centralised to avoid duplicated-literal smell.
_CHECK_TYPE_FK = "checks.CheckType"
_TRAIT_FK = "traits.Trait"


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
