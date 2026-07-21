"""Worship foundation models (#2355) and miracles (#2360).

Gods, spirits, totems, and dark powers as authorable entities (``WorshippedBeing``)
that accumulate worship in a vast resonance pool, fed by ceremonies (#2289) and
future worship acts. Beings are deliberately NOT CharacterSheets (see the ADR in
this PR): most gods are never played; the rare manifested god links an
``avatar_sheet``. Consumers (ceremonies, miracles) point INTO this app; it imports
no consumer system (ADR-0010).
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.managers import ArxSharedMemoryManager
from world.magic.models.techniques import (
    AbstractAppliedCondition,
    AbstractCapabilityGrant,
    AbstractDamageProfile,
)
from world.worship.constants import MiracleTrigger


class WorshipTradition(SharedMemoryModel):
    """A style of worship (PLACEHOLDER names: Liturgy/Spiritcalling/Druidry/Occultism).

    Bridges a being to the Rites specialization its ceremonies roll with.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(
        blank=True, help_text="PLACEHOLDER lore — Apostate rewrite pending."
    )
    rites_specialization = models.ForeignKey(
        "skills.Specialization",
        on_delete=models.PROTECT,
        related_name="worship_traditions",
        help_text="The Rites specialization ceremonies of this tradition roll with.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class WorshippedBeing(SharedMemoryModel):
    """A worshippable god/spirit/power with a vast accumulating resonance pool.

    ``resonance_pool`` is spendable by the future miracles system (#2360);
    ``lifetime_worship`` is the monotonic audit twin (mirrors the
    balance/lifetime_earned split on ``CharacterResonance``).
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(
        blank=True, help_text="PLACEHOLDER lore — Apostate rewrite pending."
    )
    tradition = models.ForeignKey(WorshipTradition, on_delete=models.PROTECT, related_name="beings")
    resonance_pool = models.BigIntegerField(
        default=0, help_text="Spendable accumulated worship (miracles draw here, #2360)."
    )
    lifetime_worship = models.BigIntegerField(
        default=0, help_text="Monotonic total worship ever received (audit)."
    )
    avatar_sheet = models.OneToOneField(
        "character_sheets.CharacterSheet",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="avatar_of_being",
        help_text="Rare: the NPC sheet a manifested god is played through.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class WorshipGrant(SharedMemoryModel):
    """Audit ledger row for worship received by a being (mirrors ResonanceGrant)."""

    being = models.ForeignKey(WorshippedBeing, on_delete=models.PROTECT, related_name="grants")
    amount = models.PositiveIntegerField()
    granted_by = models.ForeignKey(
        "character_sheets.CharacterSheet",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="worship_grants",
    )
    reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.amount} to {self.being} ({self.reason or 'unspecified'})"


class DevotionStanding(SharedMemoryModel):
    """One-way PC→god relationship: accumulated favor from worship acts.

    Deliberately NOT a ``CharacterRelationship`` (hard-typed sheet↔sheet); a god
    only enters that machinery via an ``avatar_sheet``. Miracles (#2360) read
    favor; the God's Favorite achievement tracks the per-being top (Decision 6).
    """

    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="devotion_standings",
    )
    being = models.ForeignKey(
        WorshippedBeing, on_delete=models.CASCADE, related_name="devotion_standings"
    )
    favor = models.IntegerField(default=0)
    lifetime_favor = models.IntegerField(default=0)

    class Meta:
        ordering = ["-favor"]
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet", "being"], name="unique_devotion_standing"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.character_sheet} → {self.being}: {self.favor}"


class WorshipDeclaration(SharedMemoryModel):
    """A character's declared worship: public front + optional secret truth.

    Set at CG (#2355); the secret side mints a ``Secret`` (same pattern as
    secret-by-default distinctions). ``secret_being`` is never serialized to
    non-owners — the sheet API exposes the public name only.
    """

    character_sheet = models.OneToOneField(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="worship_declaration",
    )
    public_being = models.ForeignKey(
        WorshippedBeing,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="public_worshippers",
    )
    secret_being = models.ForeignKey(
        WorshippedBeing,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="secret_worshippers",
    )
    secret = models.ForeignKey(
        "secrets.Secret",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="The minted worship Secret when secret_being is set.",
    )

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        public = self.public_being.name if self.public_being else "none"
        return f"{self.character_sheet}: {public}"


class DivineInterventionConfig(SharedMemoryModel):
    """Singleton config for divine intervention tuning (#2360).

    Staff-tunable knobs: favor threshold for trigger installation,
    per-character cooldown, minimum pool for any miracle.
    """

    objects = ArxSharedMemoryManager()

    favor_threshold = models.PositiveIntegerField(
        default=50,
        help_text="Minimum DevotionStanding.favor to install the intervention trigger.",
    )
    cooldown_hours = models.PositiveIntegerField(
        default=24,
        help_text="Per-character cooldown between interventions (hours).",
    )
    min_pool_for_intervention = models.PositiveIntegerField(
        default=100,
        help_text="Minimum resonance_pool a being must have to perform any miracle.",
    )

    class Meta:
        verbose_name = "Divine Intervention Config"
        verbose_name_plural = "Divine Intervention Config"

    def __str__(self) -> str:
        return f"DivineInterventionConfig(favor>={self.favor_threshold}, cd={self.cooldown_hours}h)"


class Miracle(SharedMemoryModel):
    """An authored miracle a WorshippedBeing can perform (#2360).

    Miracles spend from the being's ``resonance_pool``. Effects are authored
    as payload rows (conditions, capabilities, damage profiles) reusing the
    Abstract* bases from ``world.magic.models.techniques``.
    """

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    being = models.ForeignKey(
        WorshippedBeing,
        on_delete=models.PROTECT,
        related_name="miracles",
    )
    resonance_pool_cost = models.PositiveIntegerField(
        help_text="Amount deducted from being.resonance_pool when performed.",
    )
    intervention_trigger = models.CharField(
        max_length=20,
        choices=MiracleTrigger.choices,
        help_text="Danger context this miracle responds to.",
    )
    favor_threshold = models.PositiveIntegerField(
        default=50,
        help_text="Minimum DevotionStanding.favor required for this miracle to fire.",
    )
    narrative_text = models.TextField(
        help_text="Narrative broadcast (EMIT) when this miracle fires.",
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["being", "sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["being", "name"],
                name="unique_miracle_per_being_name",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.being})"


class MiracleCapabilityGrant(AbstractCapabilityGrant):
    """Capability grant payload row for a Miracle (#2360).

    INERT until a capability-read-path issue is built — mirrors
    SignatureMotifBonusCapabilityGrant inertness.
    """

    miracle = models.ForeignKey(
        Miracle,
        on_delete=models.CASCADE,
        related_name="capability_grants",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["miracle", "capability"],
                name="miracle_cap_grant_unique",
            ),
        ]


class MiracleAppliedCondition(AbstractAppliedCondition):
    """Applied condition payload row for a Miracle (#2360).

    The MVP mechanical effect surface for divine intervention.
    """

    miracle = models.ForeignKey(
        Miracle,
        on_delete=models.CASCADE,
        related_name="condition_applications",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["miracle", "condition", "target_kind"],
                name="miracle_applied_condition_unique",
            ),
        ]


class MiracleDamageProfile(AbstractDamageProfile):
    """Damage profile payload row for a Miracle (#2360)."""

    miracle = models.ForeignKey(
        Miracle,
        on_delete=models.CASCADE,
        related_name="damage_profiles",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["miracle", "damage_type"],
                condition=models.Q(damage_type__isnull=False),
                name="miracle_damage_profile_per_type",
            ),
            models.UniqueConstraint(
                fields=["miracle"],
                condition=models.Q(damage_type__isnull=True),
                name="miracle_untyped_damage_profile",
            ),
        ]


class MiraclePerformance(SharedMemoryModel):
    """Immutable audit row for each miracle firing (#2360)."""

    miracle = models.ForeignKey(Miracle, on_delete=models.PROTECT, related_name="performances")
    being = models.ForeignKey(
        WorshippedBeing, on_delete=models.PROTECT, related_name="miracle_performances"
    )
    target_character = models.ForeignKey(
        "character_sheets.CharacterSheet",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="miracle_performances",
    )
    scene = models.ForeignKey(
        "scenes.Scene",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="miracle_performances",
    )
    resonance_spent = models.PositiveIntegerField()
    trigger_event = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Miracle Performance"
        verbose_name_plural = "Miracle Performances"

    def __str__(self) -> str:
        return f"{self.miracle} → {self.target_character} ({self.trigger_event})"
