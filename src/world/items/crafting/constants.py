"""Constants for the crafting submodule."""

from decimal import Decimal

from django.db import models

#: A craft whose resolved quality tier's ``stat_multiplier`` meets this is a
#: "masterwork" — it earns the maker renown (#2243). PLACEHOLDER magnitude.
MASTERWORK_STAT_MULTIPLIER_THRESHOLD: Decimal = Decimal("1.5")

#: Legend ``base_value`` for the solo deed a masterwork craft earns its maker.
#: PLACEHOLDER — the tuning pass sets the real fame weight.
MASTERWORK_DEED_BASE_VALUE: int = 10


class CraftingRecipeKind(models.TextChoices):
    """What a CraftingRecipe produces / how it is applied.

    Room for future kinds (e.g. ALCHEMY, WAND) without schema change.
    """

    FACET_ATTACH = "facet_attach", "Facet Attach"
    STYLE_ATTACH = "style_attach", "Style Attach"
    ITEM_CREATE = "item_create", "Item Create"
    GEM_CUT = "gem_cut", "Gem Cut"


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
