"""Constants for the crafting submodule."""

from django.db import models


class CraftingRecipeKind(models.TextChoices):
    """What a CraftingRecipe produces / how it is applied.

    Room for future kinds (e.g. ALCHEMY, WAND) without schema change.
    """

    FACET_ATTACH = "facet_attach", "Facet Attach"
    STYLE_ATTACH = "style_attach", "Style Attach"


class CostConsumption(models.TextChoices):
    """How ingredient items are consumed when a crafting attempt resolves."""

    NONE = "none", "None"
    PARTIAL = "partial", "Partial"
    FULL = "full", "Full"


#: Fraction of ingredient cost charged for PARTIAL consumption outcomes.
PARTIAL_FRACTION: float = 0.5

#: Station durability ceiling scales linearly with RoomFeatureInstance.level.
#: L1 Lab = 20 crafting attempts before breaking, L5 = 100.
LAB_BASE_DURABILITY_PER_LEVEL: int = 20

#: Repair cost in coppers, per durability point restored, per station level.
#: A higher-tier Lab is pricier to restore per point (Decision 5, #1234).
LAB_REPAIR_COPPER_PER_POINT_PER_LEVEL: int = 15
