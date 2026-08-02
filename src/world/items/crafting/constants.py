"""Constants for the crafting submodule."""

from decimal import Decimal

from django.db import models

#: A craft whose resolved quality tier's ``stat_multiplier`` meets this is a
#: "masterwork" — it earns the maker renown (#2243). PLACEHOLDER magnitude.
MASTERWORK_STAT_MULTIPLIER_THRESHOLD: Decimal = Decimal("1.5")

#: Legend ``base_value`` for the solo deed a masterwork craft earns its maker.
#: PLACEHOLDER — the tuning pass sets the real fame weight.
MASTERWORK_DEED_BASE_VALUE: int = 10

#: Per-Accent-rung multiplier on the first-making fame value (#2878).
#: PLACEHOLDER — the tuning pass sets the real weight.
CRAFTING_FAME_ACCENT_WEIGHT: float = 0.2


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

#: Thread-capped crafting ceilings (#2878). A crafter's reachable rung on each
#: ladder is the base below plus one per thread woven into the recipe's
#: ``skill_trait``. Rung = ``QualityTier.sort_order`` (ladder seeded 1..12,
#: divine = 10) and ``AccentLevel.level`` (1..7). The mundane ceiling
#: deliberately stops short of divine: divine and above require the Gifted.
BASE_MAX_QUALITY_RUNG: int = 9
BASE_MAX_ACCENT_LEVEL: int = 4

#: Each Accent the crafter works into a piece raises the craft difficulty by
#: this much (#2878) — ambition is priced in probability, and "alluring AND
#: menacing" is a master's flex. PLACEHOLDER tuning.
ACCENT_DIFFICULTY_STEP: int = 5

#: Accent-check quality score → AccentLevel rung divisor (#2878). A score of
#: 15-29 realizes level 1, 30-44 level 2, … PLACEHOLDER tuning.
ACCENT_SCORE_PER_LEVEL: int = 15

#: Refinement (#2878, guaranteed long road): the progress threshold to raise a
#: piece one rung is ``max(1, item value × target rung // 100)`` — money
#: contributions convert at the projects app's 1 progress per 100 coppers, so
#: total coin ≈ item value × target rung: the road gets longer and costlier as
#: the target rises, and refining alaricite costs alaricite money. No rolls —
#: the accumulator is deterministic (Apostate's ruling). PLACEHOLDER curve.
REFINEMENT_VALUE_PER_PROGRESS: int = 100

#: Each accent on a piece multiplies its refinement threshold by this
#: (#2886): 2 accents = 4× the road. PLACEHOLDER tuning.
ACCENT_REFINEMENT_COST_BASE: int = 2

#: Refinement time horizon: instant-completion means the deadline only prunes
#: abandoned projects on the cron sweep. PLACEHOLDER.
REFINEMENT_TIME_LIMIT_DAYS: int = 365

#: Station durability ceiling scales linearly with RoomFeatureInstance.level.
#: L1 Lab = 20 crafting attempts before breaking, L5 = 100.
LAB_BASE_DURABILITY_PER_LEVEL: int = 20

#: Repair cost in coppers, per durability point restored, per station level.
#: A higher-tier Lab is pricier to restore per point (Decision 5, #1234).
LAB_REPAIR_COPPER_PER_POINT_PER_LEVEL: int = 15
