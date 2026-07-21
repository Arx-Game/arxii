"""Models for the agriculture (crop/food) system.

The Field + Granary are a coupled pair of RoomFeatureKinds implementing an
accrue-then-collect food system. The Field accrues food into an
``uncollected_pool`` on a daily cron tick; a character actively collects it
via a lossy check-based dispatch (mirrors ``collect_org_income``); the
Granary's level gates storage capacity; a domain's population consumes food
weekly with shortage raising unrest and lowering prosperity.
"""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

# App-qualified model path repeated across FK references; centralized for dedup.
_DOMAIN_MODEL = "societies.Domain"


class CropType(SharedMemoryModel):
    """Staff-authored catalog of crop varieties.

    Each row pairs a ``base_production`` (per-tick base yield before level
    and config scaling) with a name and description. Content-authorable;
    no code change needed to add a new crop.
    """

    name = models.CharField(max_length=100, unique=True)
    base_production = models.PositiveIntegerField(
        help_text="Per-tick base yield before level × config scaling.",
    )
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class FieldDetails(SharedMemoryModel):
    """Per-(FIELD RoomFeatureInstance) details payload.

    Created when a Field is installed via the ROOM_FEATURE_PROGRESSION
    project. OneToOne back to the framework's ``RoomFeatureInstance`` —
    the install/upgrade flow lives in ``world.room_features``; the
    per-kind state (crop type + uncollected pool) lives here.
    """

    feature_instance = models.OneToOneField(
        "room_features.RoomFeatureInstance",
        on_delete=models.CASCADE,
        related_name="field_details",
        primary_key=True,
    )
    crop_type = models.ForeignKey(
        CropType,
        on_delete=models.PROTECT,
        related_name="fields",
    )
    uncollected_pool = models.PositiveIntegerField(
        default=0,
        help_text="Accrued food awaiting active collection.",
    )

    def __str__(self) -> str:
        return f"Field ({self.crop_type.name}) pool={self.uncollected_pool}"


class GranaryDetails(SharedMemoryModel):
    """Per-(GRANARY RoomFeatureInstance) details payload.

    No stored-amount field — the domain-level ``FoodStockpile`` holds the
    balance. The Granary's contribution is its level → capacity mapping,
    derived at read time via ``max_food_capacity(domain)``.
    """

    feature_instance = models.OneToOneField(
        "room_features.RoomFeatureInstance",
        on_delete=models.CASCADE,
        related_name="granary_details",
        primary_key=True,
    )

    def __str__(self) -> str:
        return f"Granary @ {self.feature_instance_id}"


class FoodStockpile(SharedMemoryModel):
    """A domain's food balance.

    Lazily created via ``get_or_create`` inside ``collect_field_food`` on
    first collection. A domain with Fields but no prior collection has no
    stockpile row; ``domain_consumption_tick`` treats the absence of a
    stockpile as perpetual shortage.
    """

    domain = models.OneToOneField(
        _DOMAIN_MODEL,
        on_delete=models.CASCADE,
        related_name="food_stockpile",
        primary_key=True,
    )
    stored = models.PositiveIntegerField(default=0)
    last_collected_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"FoodStockpile({self.domain_id}): {self.stored}"


class FoodConfig(SharedMemoryModel):
    """Singleton tuning config (pk=1) for the agriculture system.

    Lazy-created via ``get_food_config()`` in ``services/__init__.py``.
    All magnitudes are PLACEHOLDER — tune via admin.
    """

    production_rate_multiplier = models.PositiveIntegerField(
        default=1,
        help_text="Global scalar on Field production (integer, 1=×1).",
    )
    consumption_per_capita = models.PositiveIntegerField(
        default=1,
        help_text="Food consumed per population unit per week.",
    )
    shortage_unrest_penalty = models.PositiveSmallIntegerField(
        default=5,
        help_text="Unrest added per week of food shortage.",
    )
    shortage_prosperity_penalty = models.PositiveSmallIntegerField(
        default=5,
        help_text="Prosperity subtracted per week of food shortage.",
    )
    recovery_unrest_relief = models.PositiveSmallIntegerField(
        default=2,
        help_text="Unrest relaxed per well-fed week (recovery drift, #2238).",
    )
    recovery_prosperity_gain = models.PositiveSmallIntegerField(
        default=2,
        help_text="Prosperity recovered per well-fed week, up to the equilibrium.",
    )
    prosperity_equilibrium = models.PositiveSmallIntegerField(
        default=50,
        help_text="Baseline a well-fed domain's prosperity recovers toward (never past; "
        "improvements above it are untouched).",
    )
    granary_capacity_per_level = models.PositiveIntegerField(
        default=100,
        help_text="Max stored food per Granary level.",
    )
    # Pool-size difficulty scaling (#2218): a larger accumulated pool is harder
    # to collect — more food means more laborers, carts, and attention drawn.
    # All PLACEHOLDER — tune via admin.
    pool_difficulty_threshold = models.PositiveIntegerField(
        default=50,
        help_text=(
            "Pool size above which difficulty begins to ramp "
            "(the first 'step' boundary). PLACEHOLDER."
        ),
    )
    pool_difficulty_step = models.PositiveIntegerField(
        default=50,
        help_text=(
            "Each full step of pool size above the threshold adds one "
            "difficulty point. PLACEHOLDER."
        ),
    )
    pool_difficulty_max_bonus = models.PositiveSmallIntegerField(
        default=30,
        help_text=("Cap on the total difficulty bonus from pool size. PLACEHOLDER."),
    )
    army_food_per_member = models.PositiveIntegerField(
        default=10,
        help_text="Food consumed per engaged covenant member at army mobilization. PLACEHOLDER.",
    )
    max_provisioning_morale_penalty = models.PositiveSmallIntegerField(
        default=30,
        help_text="Maximum morale points subtracted from units at zero provisioning. PLACEHOLDER.",
    )
    max_provisioning_strength_penalty = models.PositiveSmallIntegerField(
        default=30,
        help_text=(
            "Maximum strength points subtracted from units at zero provisioning. PLACEHOLDER."
        ),
    )
    crew_food_per_leg = models.PositiveIntegerField(
        default=5,
        help_text="Food consumed per crew member per voyage leg. PLACEHOLDER.",
    )
    ship_provisioning_ap_surcharge = models.PositiveSmallIntegerField(
        default=50,
        help_text=(
            "Max AP surcharge percentage at zero provisioning "
            "(50 = up to 50% extra AP). PLACEHOLDER."
        ),
    )

    class Meta:
        verbose_name = "Food Config"

    def __str__(self) -> str:
        return "Food Config (singleton)"


class FoodTransfer(SharedMemoryModel):
    """Audit row for every inter-domain food transfer (#2219).

    Mirrors ``CurrencyTransfer``'s audit-trail pattern: every food
    movement between domains is logged with source, target, amount,
    and acting persona.
    """

    source_domain = models.ForeignKey(
        _DOMAIN_MODEL,
        on_delete=models.CASCADE,
        related_name="food_transfers_out",
    )
    target_domain = models.ForeignKey(
        _DOMAIN_MODEL,
        on_delete=models.CASCADE,
        related_name="food_transfers_in",
    )
    amount = models.PositiveIntegerField(help_text="Food units moved.")
    acting_persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="food_transfers_initiated",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"FoodTransfer({self.source_domain_id}→{self.target_domain_id}: {self.amount})"
