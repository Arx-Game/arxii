"""Threads and thread-pull infrastructure.

Per-character Thread rows anchored to a trait/technique/relationship/facet/covenant-role.
ThreadLevelUnlock is the per-thread XP-locked-boundary receipt.
ThreadPullCost is the per-tier pull-cost tuning table.
ThreadXPLockedLevel is the XP-locked boundary price list.
ThreadPullEffect is the authored pull-effect template.
"""

from decimal import Decimal
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.magic.constants import (
    EffectKind,
    RegardPolarity,
    SanctumSlotKind,
    TargetKind,
    VitalBonusTarget,
)

if TYPE_CHECKING:
    from world.conditions.models import CapabilityType


class ThreadPullCost(SharedMemoryModel):
    """Per-tier pull cost. Three rows at launch (tier 1/2/3).

    Pull-cost tuning surface — see Spec A §2.1 / §5.4 step 2. Per-tier
    numbers (resonance_cost, anima_per_thread) live here as data; the
    cost-formula shape lives in spend_resonance_for_pull. Edit values
    here for per-tier tweaks; edit the service for shape changes.

    The optional ``target_kind`` scopes a row to a specific thread kind
    (ADR-0051: gift-threads are the costliest kind). A row with
    ``target_kind=None`` is the universal default that applies to all
    kinds without a kind-specific row. Resolvers prefer a kind-specific
    row and fall back to the universal row (mirrors the
    ``ThreadPullEffect.target_gift`` lookup pattern).

    ``imbue_cost_multiplier`` (default 1) scales the imbue dp formula
    for this kind — so GIFT threads cost more to raise via imbuing too.
    """

    tier = models.PositiveSmallIntegerField()
    target_kind = models.CharField(
        max_length=32,
        choices=TargetKind.choices,
        null=True,
        blank=True,
    )
    resonance_cost = models.PositiveSmallIntegerField()
    anima_per_thread = models.PositiveSmallIntegerField()
    imbue_cost_multiplier = models.PositiveSmallIntegerField(default=1)
    label = models.CharField(max_length=32)

    class Meta:
        ordering = ("tier", "target_kind")
        constraints = [
            # Universal default rows: one per tier (target_kind=None).
            models.UniqueConstraint(
                fields=["tier"],
                condition=models.Q(target_kind__isnull=True),
                name="threadpullcost_tier_universal",
            ),
            # Kind-specific rows: one per (tier, target_kind).
            models.UniqueConstraint(
                fields=["tier", "target_kind"],
                condition=models.Q(target_kind__isnull=False),
                name="threadpullcost_tier_kind",
            ),
        ]

    def __str__(self) -> str:
        if self.target_kind:
            return f"Tier {self.tier} ({self.label}, {self.target_kind})"
        return f"Tier {self.tier} ({self.label})"


class ThreadXPLockedLevel(SharedMemoryModel):
    """XP-locked boundary on the internal level scale. Mirrors skills XP locks."""

    level = models.PositiveSmallIntegerField(unique=True)
    xp_cost = models.PositiveIntegerField()

    class Meta:
        ordering = ("level",)

    def __str__(self) -> str:
        return f"Lvl {self.level} (XP {self.xp_cost})"


class ThreadPullEffect(SharedMemoryModel):
    """Authored pull-effect template.

    Tier 0 is passive (always-on while anchor is in scope); tiers 1-3 are
    paid pulls. Lookup row keyed (target_kind, resonance, tier, min_thread_level).
    Payload columns are mutually exclusive per effect_kind; clean() enforces
    the legal combinations and DB CheckConstraints mirror the validation.

    ``target_gift`` scopes a row to a specific Gift (GIFT target_kind only).
    Resolvers prefer gift-specific rows over null-target_gift rows (universal
    fallback) when both exist for the same base key. Null = applies to all
    threads matching the key (existing covenant/sanctum behavior unchanged).
    """

    target_kind = models.CharField(max_length=32, choices=TargetKind.choices)
    resonance = models.ForeignKey(
        "magic.Resonance",
        on_delete=models.PROTECT,
        related_name="pull_effects",
    )
    tier = models.PositiveSmallIntegerField()  # 0..3
    min_thread_level = models.PositiveSmallIntegerField(default=0)
    effect_kind = models.CharField(max_length=32, choices=EffectKind.choices)

    flat_bonus_amount = models.SmallIntegerField(null=True, blank=True)
    intensity_bump_amount = models.SmallIntegerField(null=True, blank=True)
    vital_bonus_amount = models.SmallIntegerField(null=True, blank=True)
    vital_target = models.CharField(
        max_length=32,
        choices=VitalBonusTarget.choices,
        null=True,
        blank=True,
    )
    capability_grant = models.ForeignKey(
        "conditions.CapabilityType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="thread_pull_effects",
    )
    narrative_snippet = models.TextField(blank=True)
    target_form = models.ForeignKey(
        "forms.CharacterForm",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="pull_effect_targets",
        help_text="The form whose combat profiles are selected for ASSUME_ALTERNATE_SELF.",
    )
    resistance_amount = models.SmallIntegerField(null=True, blank=True)
    resistance_damage_type = models.ForeignKey(
        "conditions.DamageType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="thread_pull_resistances",
        help_text="Damage type this resistance applies to. Null = all damage types.",
    )
    target_gift = models.ForeignKey(
        "magic.Gift",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="thread_pull_effects",
        help_text=(
            "Gift-specific pull effect (GIFT target_kind only). Null = applies to all "
            "threads matching the lookup key (existing covenant/sanctum behavior)."
        ),
    )
    regard_polarity = models.CharField(
        max_length=16,
        choices=RegardPolarity.choices,
        default=RegardPolarity.NEUTRAL,
        help_text=(
            "How Court-role (COVENANT_ROLE) pull modulation responds to the leader's "
            "signed regard for the target. Ignored for other thread kinds."
        ),
    )

    class Meta:
        indexes = [
            models.Index(fields=["target_kind", "resonance", "tier"]),
        ]
        constraints = [
            # Two partial UniqueConstraints replace the original single constraint so
            # that Postgres treats NULL target_gift rows as unique (one per base key)
            # while also allowing one row per (base key, specific gift). Without the
            # condition= split, Postgres would treat NULLs as DISTINCT and allow
            # duplicate null-target_gift rows — silently breaking covenant lookups.
            # Pattern mirrors the per-kind partial constraints on Thread in this file.
            models.UniqueConstraint(
                fields=["target_kind", "resonance", "tier", "min_thread_level"],
                condition=models.Q(target_gift__isnull=True),
                name="threadpulleffect_lookup_key",  # keep name: existing rows unchanged
            ),
            models.UniqueConstraint(
                fields=["target_kind", "resonance", "tier", "min_thread_level", "target_gift"],
                condition=models.Q(target_gift__isnull=False),
                name="threadpulleffect_lookup_key_gift",
            ),
            # FLAT_BONUS: requires flat_bonus_amount, forbids other payloads.
            models.CheckConstraint(
                check=(
                    ~models.Q(effect_kind="FLAT_BONUS")
                    | (
                        models.Q(flat_bonus_amount__isnull=False)
                        & models.Q(intensity_bump_amount__isnull=True)
                        & models.Q(vital_bonus_amount__isnull=True)
                        & models.Q(vital_target__isnull=True)
                        & models.Q(capability_grant__isnull=True)
                        & models.Q(target_form__isnull=True)
                        & models.Q(resistance_amount__isnull=True)
                    )
                ),
                name="threadpulleffect_flat_bonus_payload",
            ),
            # INTENSITY_BUMP: requires intensity_bump_amount, forbids others.
            models.CheckConstraint(
                check=(
                    ~models.Q(effect_kind="INTENSITY_BUMP")
                    | (
                        models.Q(intensity_bump_amount__isnull=False)
                        & models.Q(flat_bonus_amount__isnull=True)
                        & models.Q(vital_bonus_amount__isnull=True)
                        & models.Q(vital_target__isnull=True)
                        & models.Q(capability_grant__isnull=True)
                        & models.Q(target_form__isnull=True)
                        & models.Q(resistance_amount__isnull=True)
                    )
                ),
                name="threadpulleffect_intensity_bump_payload",
            ),
            # VITAL_BONUS: requires vital_bonus_amount + vital_target, forbids others.
            models.CheckConstraint(
                check=(
                    ~models.Q(effect_kind="VITAL_BONUS")
                    | (
                        models.Q(vital_bonus_amount__isnull=False)
                        & models.Q(vital_target__isnull=False)
                        & models.Q(flat_bonus_amount__isnull=True)
                        & models.Q(intensity_bump_amount__isnull=True)
                        & models.Q(capability_grant__isnull=True)
                        & models.Q(target_form__isnull=True)
                        & models.Q(resistance_amount__isnull=True)
                    )
                ),
                name="threadpulleffect_vital_bonus_payload",
            ),
            # CAPABILITY_GRANT: requires capability_grant FK, forbids numeric payloads.
            models.CheckConstraint(
                check=(
                    ~models.Q(effect_kind="CAPABILITY_GRANT")
                    | (
                        models.Q(capability_grant__isnull=False)
                        & models.Q(flat_bonus_amount__isnull=True)
                        & models.Q(intensity_bump_amount__isnull=True)
                        & models.Q(vital_bonus_amount__isnull=True)
                        & models.Q(vital_target__isnull=True)
                        & models.Q(target_form__isnull=True)
                        & models.Q(resistance_amount__isnull=True)
                    )
                ),
                name="threadpulleffect_capability_grant_payload",
            ),
            # NARRATIVE_ONLY: requires non-empty snippet, forbids all other payloads.
            models.CheckConstraint(
                check=(
                    ~models.Q(effect_kind="NARRATIVE_ONLY")
                    | (
                        ~models.Q(narrative_snippet="")
                        & models.Q(flat_bonus_amount__isnull=True)
                        & models.Q(intensity_bump_amount__isnull=True)
                        & models.Q(vital_bonus_amount__isnull=True)
                        & models.Q(vital_target__isnull=True)
                        & models.Q(capability_grant__isnull=True)
                        & models.Q(target_form__isnull=True)
                        & models.Q(resistance_amount__isnull=True)
                    )
                ),
                name="threadpulleffect_narrative_only_payload",
            ),
            # CORRUPTION_RESISTANCE: no payload column — runtime value derives from
            # CharacterResonance.lifetime_helped (Spec B §15.3). All payload columns null.
            models.CheckConstraint(
                check=(
                    ~models.Q(effect_kind="CORRUPTION_RESISTANCE")
                    | (
                        models.Q(flat_bonus_amount__isnull=True)
                        & models.Q(intensity_bump_amount__isnull=True)
                        & models.Q(vital_bonus_amount__isnull=True)
                        & models.Q(vital_target__isnull=True)
                        & models.Q(capability_grant__isnull=True)
                        & models.Q(target_form__isnull=True)
                        & models.Q(resistance_amount__isnull=True)
                    )
                ),
                name="threadpulleffect_corruption_resistance_payload",
            ),
            # ASSUME_ALTERNATE_SELF: no numeric payload; requires a target form.
            models.CheckConstraint(
                check=(
                    ~models.Q(effect_kind="ASSUME_ALTERNATE_SELF")
                    | (
                        models.Q(target_form__isnull=False)
                        & models.Q(flat_bonus_amount__isnull=True)
                        & models.Q(intensity_bump_amount__isnull=True)
                        & models.Q(vital_bonus_amount__isnull=True)
                        & models.Q(vital_target__isnull=True)
                        & models.Q(capability_grant__isnull=True)
                        & models.Q(narrative_snippet="")
                        & models.Q(resistance_amount__isnull=True)
                    )
                ),
                name="threadpulleffect_assume_alternate_self_payload",
            ),
            # RESISTANCE: requires resistance_amount; forbids all other exclusive payloads.
            # resistance_damage_type is optional (null = all damage types).
            models.CheckConstraint(
                check=(
                    ~models.Q(effect_kind="RESISTANCE")
                    | (
                        models.Q(resistance_amount__isnull=False)
                        & models.Q(flat_bonus_amount__isnull=True)
                        & models.Q(intensity_bump_amount__isnull=True)
                        & models.Q(vital_bonus_amount__isnull=True)
                        & models.Q(vital_target__isnull=True)
                        & models.Q(capability_grant__isnull=True)
                        & models.Q(target_form__isnull=True)
                    )
                ),
                name="threadpulleffect_resistance_payload",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"PullEffect(t={self.target_kind} res={self.resonance_id} "
            f"tier={self.tier} kind={self.effect_kind})"
        )

    def clean(self) -> None:
        super().clean()
        numeric_fields: dict[str, int | None] = {
            "flat_bonus_amount": self.flat_bonus_amount,
            "intensity_bump_amount": self.intensity_bump_amount,
            "vital_bonus_amount": self.vital_bonus_amount,
        }
        validators = {
            EffectKind.FLAT_BONUS: self._clean_flat_bonus,
            EffectKind.INTENSITY_BUMP: self._clean_intensity_bump,
            EffectKind.VITAL_BONUS: self._clean_vital_bonus,
            EffectKind.CAPABILITY_GRANT: self._clean_capability_grant,
            EffectKind.NARRATIVE_ONLY: self._clean_narrative_only,
            EffectKind.ASSUME_ALTERNATE_SELF: self._clean_assume_alternate_self,
            EffectKind.RESISTANCE: self._clean_resistance,
            # CORRUPTION_RESISTANCE: no payload validator needed — runtime value
            # derives from CharacterResonance.lifetime_helped (Spec B §15.3).
            # The DB CheckConstraint enforces all payload columns are null.
        }
        validator = validators.get(self.effect_kind)
        if validator is not None:
            validator(numeric_fields)

    def _clean_flat_bonus(self, numeric_fields: dict[str, int | None]) -> None:
        self._require_only("flat_bonus_amount", numeric_fields, self.capability_grant)
        if self.resistance_amount is not None:
            raise ValidationError({"resistance_amount": "Must be null for FLAT_BONUS."})

    def _clean_intensity_bump(self, numeric_fields: dict[str, int | None]) -> None:
        self._require_only("intensity_bump_amount", numeric_fields, self.capability_grant)
        if self.resistance_amount is not None:
            raise ValidationError({"resistance_amount": "Must be null for INTENSITY_BUMP."})

    def _clean_vital_bonus(self, numeric_fields: dict[str, int | None]) -> None:
        self._require_only("vital_bonus_amount", numeric_fields, self.capability_grant)
        if not self.vital_target:
            raise ValidationError({"vital_target": "VITAL_BONUS requires vital_target."})
        if self.resistance_amount is not None:
            raise ValidationError({"resistance_amount": "Must be null for VITAL_BONUS."})

    def _clean_capability_grant(self, numeric_fields: dict[str, int | None]) -> None:
        if self.capability_grant is None:
            raise ValidationError(
                {"capability_grant": "CAPABILITY_GRANT requires capability_grant."}
            )
        for name, val in numeric_fields.items():
            if val is not None:
                raise ValidationError({name: "Must be null for CAPABILITY_GRANT."})
        if self.resistance_amount is not None:
            raise ValidationError({"resistance_amount": "Must be null for CAPABILITY_GRANT."})

    def _clean_narrative_only(self, numeric_fields: dict[str, int | None]) -> None:
        if not self.narrative_snippet.strip():
            raise ValidationError({"narrative_snippet": "NARRATIVE_ONLY requires snippet."})
        if self.capability_grant is not None:
            raise ValidationError({"capability_grant": "Must be null for NARRATIVE_ONLY."})
        for name, val in numeric_fields.items():
            if val is not None:
                raise ValidationError({name: "Must be null for NARRATIVE_ONLY."})
        if self.resistance_amount is not None:
            raise ValidationError({"resistance_amount": "Must be null for NARRATIVE_ONLY."})

    def _clean_assume_alternate_self(self, numeric_fields: dict[str, int | None]) -> None:
        if self.target_form is None:
            raise ValidationError({"target_form": "ASSUME_ALTERNATE_SELF requires target_form."})
        if self.capability_grant is not None:
            raise ValidationError({"capability_grant": "Must be null for ASSUME_ALTERNATE_SELF."})
        if self.narrative_snippet.strip():
            raise ValidationError({"narrative_snippet": "Must be blank for ASSUME_ALTERNATE_SELF."})
        for name, val in numeric_fields.items():
            if val is not None:
                raise ValidationError({name: "Must be null for ASSUME_ALTERNATE_SELF."})
        if self.resistance_amount is not None:
            raise ValidationError({"resistance_amount": "Must be null for ASSUME_ALTERNATE_SELF."})

    def _clean_resistance(self, numeric_fields: dict[str, int | None]) -> None:
        if self.resistance_amount is None:
            raise ValidationError({"resistance_amount": "RESISTANCE requires resistance_amount."})
        for name, val in numeric_fields.items():
            if val is not None:
                raise ValidationError({name: "Must be null for RESISTANCE."})
        if self.capability_grant is not None:
            raise ValidationError({"capability_grant": "Must be null for RESISTANCE."})
        if self.target_form is not None:
            raise ValidationError({"target_form": "Must be null for RESISTANCE."})
        # resistance_damage_type is optional (null = all damage types) — no check needed.

    @staticmethod
    def _require_only(
        name: str,
        numeric_fields: dict[str, int | None],
        capability: "CapabilityType | None",
    ) -> None:
        if numeric_fields[name] is None:
            raise ValidationError({name: f"{name} required for this effect_kind."})
        for other, val in numeric_fields.items():
            if other != name and val is not None:
                raise ValidationError({other: "Must be null for this effect_kind."})
        if capability is not None:
            raise ValidationError({"capability_grant": "Must be null for this effect_kind."})


class ThreadSurvivabilityTuning(SharedMemoryModel):
    """Per-target tuning for the universal thread survivability baseline (#1175).

    One row per ``VitalBonusTarget``. The baseline a character receives for a
    target is ``round(cap * S / (S + half_saturation))`` where
    ``S = coefficient * Σ max(1, thread.level // 10)`` over owned threads — a
    soft cap: every thread/level raises it with diminishing returns toward
    ``cap``; a lone wolf (no threads, S=0) receives 0. Real columns, no JSON;
    staff tune in admin. Seeded explicitly via
    ``seed_thread_survivability_tuning`` — inert until rows exist.
    """

    vital_target = models.CharField(
        max_length=32,
        choices=VitalBonusTarget.choices,
        unique=True,
        help_text="Which survivability vector this row tunes.",
    )
    coefficient = models.PositiveSmallIntegerField(
        default=1,
        help_text="Linear multiplier on the breadth×depth investment score S (default 1).",
    )
    cap = models.PositiveSmallIntegerField(
        help_text="Ceiling the baseline asymptotes toward at very high investment.",
    )
    half_saturation = models.PositiveSmallIntegerField(
        help_text="Investment score S at which the baseline reaches half of cap.",
    )
    coherence_scale = models.PositiveSmallIntegerField(
        default=50,
        help_text=(
            "Per-resonance coherence bonus that yields +1.0 to a thread's depth "
            "multiplier. 0 disables the fashion/motif amplifier for this target."
        ),
    )
    coherence_max_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("2.00"),
        help_text="Ceiling on the per-thread coherence multiplier (1.00 = inert).",
    )

    def __str__(self) -> str:
        return f"ThreadSurvivabilityTuning({self.vital_target})"


class Thread(SharedMemoryModel):
    """Per-character thread anchored to a trait/technique/room/relationship/facet/covenant-role.

    Discriminator + typed-FK pattern (Spec A §2.1 lines 83-151). Exactly one
    target_* column is populated, matching ``target_kind``. Three layers of
    enforcement:

    - ``clean()`` raises ValidationError on missing / mismatched targets.
    - Per-kind CheckConstraints mirror the "exactly one target_* set, matching
      target_kind" rule at the DB layer (so misuse via .objects.create() also
      fails).
    - Per-kind partial UniqueConstraints prevent duplicate threads within the
      same (owner, resonance, target_kind, target_*) combination.
    """

    owner = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.PROTECT,
        related_name="threads",
        help_text="Character who owns this thread.",
    )
    resonance = models.ForeignKey(
        "magic.Resonance",
        on_delete=models.PROTECT,
        related_name="threads",
        help_text="Resonance this thread channels.",
    )
    target_kind = models.CharField(
        max_length=32,
        choices=TargetKind.choices,
        help_text="Discriminator selecting which target_* FK is populated.",
    )

    name = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)

    developed_points = models.PositiveIntegerField(
        default=0,
        help_text="Permanent points; advances level via ThreadLevelUnlock entries.",
    )
    level = models.PositiveSmallIntegerField(
        default=0,
        help_text="Current level on the internal scale (multiples of 10).",
    )
    hollow_current = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Soul Tether Hollow capacity (Spec B §5). Only meaningful for "
            "RELATIONSHIP_CAPSTONE Sinner-side Threads. Drains on corruption "
            "redirect; refills via Sineating. Other Threads ignore this field."
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    retired_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Set when owner soft-retires this thread; retired threads are "
            "excluded from list/detail views and from all pull / passive paths."
        ),
    )

    target_trait = models.ForeignKey(
        "traits.Trait",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="anchored_threads",
        help_text="Set when target_kind=TRAIT; null otherwise.",
    )
    target_technique = models.ForeignKey(
        "magic.Technique",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="anchored_threads",
        help_text="Set when target_kind=TECHNIQUE; null otherwise.",
    )
    target_relationship_track = models.ForeignKey(
        "relationships.RelationshipTrackProgress",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="anchored_threads",
        help_text="Set when target_kind=RELATIONSHIP_TRACK; null otherwise.",
    )
    target_capstone = models.ForeignKey(
        "relationships.RelationshipCapstone",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="anchored_threads",
        help_text="Set when target_kind=RELATIONSHIP_CAPSTONE; null otherwise.",
    )
    target_facet = models.ForeignKey(
        "magic.Facet",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="anchored_threads",
        help_text="Set when target_kind=FACET; null otherwise.",
    )
    target_covenant_role = models.ForeignKey(
        "covenants.CovenantRole",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="anchored_threads",
        help_text="Set when target_kind=COVENANT_ROLE; null otherwise.",
    )
    target_gift = models.ForeignKey(
        "magic.Gift",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="anchored_threads",
        help_text="Set when target_kind=GIFT; null otherwise.",
    )
    target_mantle = models.ForeignKey(
        "items.Mantle",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="anchored_threads",
        help_text="Set when target_kind=MANTLE; null otherwise.",
    )
    target_sanctum_details = models.ForeignKey(
        "magic.SanctumDetails",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="anchored_threads",
        help_text="Set when target_kind=SANCTUM; null otherwise. Plan 4 §F.",
    )
    slot_kind = models.CharField(
        max_length=16,
        choices=SanctumSlotKind.choices,
        blank=True,
        default="",
        help_text=(
            "Per-PC weaving slot rule. Required for SANCTUM threads, must be "
            "empty for all other target_kinds. Enforced by CheckConstraint. "
            "PERSONAL_OWN + COVENANT slots are limited to one active per owner."
        ),
    )
    signature_bonus = models.ForeignKey(
        "magic.SignatureMotifBonus",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "Player-chosen SignatureMotifBonus attached to this thread. "
            "May only be non-null when target_kind=TECHNIQUE (#1582)."
        ),
    )

    class Meta:
        constraints = [
            # ---- Per-kind partial UniqueConstraints (one per TargetKind) ---------
            models.UniqueConstraint(
                fields=["owner", "resonance", "target_trait"],
                condition=models.Q(target_kind=TargetKind.TRAIT),
                name="uniq_thread_trait",
            ),
            models.UniqueConstraint(
                fields=["owner", "resonance", "target_technique"],
                condition=models.Q(target_kind=TargetKind.TECHNIQUE),
                name="uniq_thread_technique",
            ),
            models.UniqueConstraint(
                fields=["owner", "resonance", "target_relationship_track"],
                condition=models.Q(target_kind=TargetKind.RELATIONSHIP_TRACK),
                name="uniq_thread_rel_track",
            ),
            models.UniqueConstraint(
                fields=["owner", "resonance", "target_capstone"],
                condition=models.Q(target_kind=TargetKind.RELATIONSHIP_CAPSTONE),
                name="uniq_thread_rel_capstone",
            ),
            # ---- Per-kind CheckConstraints (exactly one target_* set) -----------
            models.CheckConstraint(
                name="thread_trait_payload",
                check=(
                    ~models.Q(target_kind=TargetKind.TRAIT)
                    | (
                        models.Q(target_trait__isnull=False)
                        & models.Q(target_technique__isnull=True)
                        & models.Q(target_relationship_track__isnull=True)
                        & models.Q(target_capstone__isnull=True)
                        & models.Q(target_facet__isnull=True)
                        & models.Q(target_covenant_role__isnull=True)
                        & models.Q(target_gift__isnull=True)
                        & models.Q(target_mantle__isnull=True)
                        & models.Q(target_sanctum_details__isnull=True)
                    )
                ),
            ),
            models.CheckConstraint(
                name="thread_technique_payload",
                check=(
                    ~models.Q(target_kind=TargetKind.TECHNIQUE)
                    | (
                        models.Q(target_trait__isnull=True)
                        & models.Q(target_technique__isnull=False)
                        & models.Q(target_relationship_track__isnull=True)
                        & models.Q(target_capstone__isnull=True)
                        & models.Q(target_facet__isnull=True)
                        & models.Q(target_covenant_role__isnull=True)
                        & models.Q(target_gift__isnull=True)
                        & models.Q(target_mantle__isnull=True)
                        & models.Q(target_sanctum_details__isnull=True)
                    )
                ),
            ),
            models.CheckConstraint(
                name="thread_rel_track_payload",
                check=(
                    ~models.Q(target_kind=TargetKind.RELATIONSHIP_TRACK)
                    | (
                        models.Q(target_trait__isnull=True)
                        & models.Q(target_technique__isnull=True)
                        & models.Q(target_relationship_track__isnull=False)
                        & models.Q(target_capstone__isnull=True)
                        & models.Q(target_facet__isnull=True)
                        & models.Q(target_covenant_role__isnull=True)
                        & models.Q(target_gift__isnull=True)
                        & models.Q(target_mantle__isnull=True)
                        & models.Q(target_sanctum_details__isnull=True)
                    )
                ),
            ),
            models.CheckConstraint(
                name="thread_rel_capstone_payload",
                check=(
                    ~models.Q(target_kind=TargetKind.RELATIONSHIP_CAPSTONE)
                    | (
                        models.Q(target_trait__isnull=True)
                        & models.Q(target_technique__isnull=True)
                        & models.Q(target_relationship_track__isnull=True)
                        & models.Q(target_capstone__isnull=False)
                        & models.Q(target_facet__isnull=True)
                        & models.Q(target_covenant_role__isnull=True)
                        & models.Q(target_gift__isnull=True)
                        & models.Q(target_mantle__isnull=True)
                        & models.Q(target_sanctum_details__isnull=True)
                    )
                ),
            ),
            # ---- FACET -------------------------------------------------------
            # One active thread per (owner, facet) — the chosen resonance is a
            # property of that single thread, not a second dimension of identity.
            # Retired threads (retired_at IS NOT NULL) are excluded so a character
            # can retire a Spider/Praedari thread and later weave a Spider/Brimscar
            # thread on the same facet.
            models.UniqueConstraint(
                fields=["owner", "target_facet"],
                condition=models.Q(target_kind=TargetKind.FACET, retired_at__isnull=True),
                name="uniq_thread_facet_active",
            ),
            models.CheckConstraint(
                name="thread_facet_payload",
                check=(
                    ~models.Q(target_kind=TargetKind.FACET)
                    | (
                        models.Q(target_facet__isnull=False)
                        & models.Q(target_trait__isnull=True)
                        & models.Q(target_technique__isnull=True)
                        & models.Q(target_relationship_track__isnull=True)
                        & models.Q(target_capstone__isnull=True)
                        & models.Q(target_covenant_role__isnull=True)
                        & models.Q(target_gift__isnull=True)
                        & models.Q(target_mantle__isnull=True)
                        & models.Q(target_sanctum_details__isnull=True)
                    )
                ),
            ),
            # ---- COVENANT_ROLE -----------------------------------------------
            # One active thread per (owner, covenant_role). Retired threads
            # (retired_at IS NOT NULL) are excluded so a character can retire a
            # role thread and later weave a new one on the same role.
            models.UniqueConstraint(
                fields=["owner", "target_covenant_role"],
                condition=models.Q(target_kind=TargetKind.COVENANT_ROLE, retired_at__isnull=True),
                name="uniq_thread_covenant_role_active",
            ),
            models.CheckConstraint(
                name="thread_covenant_role_payload",
                check=(
                    ~models.Q(target_kind=TargetKind.COVENANT_ROLE)
                    | (
                        models.Q(target_covenant_role__isnull=False)
                        & models.Q(target_trait__isnull=True)
                        & models.Q(target_technique__isnull=True)
                        & models.Q(target_relationship_track__isnull=True)
                        & models.Q(target_capstone__isnull=True)
                        & models.Q(target_facet__isnull=True)
                        & models.Q(target_gift__isnull=True)
                        & models.Q(target_mantle__isnull=True)
                        & models.Q(target_sanctum_details__isnull=True)
                    )
                ),
            ),
            # ---- GIFT ---------------------------------------------------------
            # One active thread per (owner, target_gift), mirroring
            # uniq_thread_covenant_role_active (one active thread per anchor).
            # Retired threads (retired_at IS NOT NULL) are excluded so a
            # character can retire a gift thread and later weave a new one on
            # the same gift. The single-thread-per-gift invariant is enforced
            # here at the DB layer (decision 7); multi-resonance (multiple
            # active GIFT threads per gift) is a deferred follow-up (#1619) and
            # would relax this constraint + make the resolver return a set.
            models.UniqueConstraint(
                fields=["owner", "target_gift"],
                condition=models.Q(
                    target_kind=TargetKind.GIFT,
                    retired_at__isnull=True,
                ),
                name="uniq_thread_gift_active",
            ),
            models.CheckConstraint(
                name="thread_gift_payload",
                check=(
                    ~models.Q(target_kind=TargetKind.GIFT)
                    | (
                        models.Q(target_gift__isnull=False)
                        & models.Q(target_trait__isnull=True)
                        & models.Q(target_technique__isnull=True)
                        & models.Q(target_relationship_track__isnull=True)
                        & models.Q(target_capstone__isnull=True)
                        & models.Q(target_facet__isnull=True)
                        & models.Q(target_covenant_role__isnull=True)
                        & models.Q(target_mantle__isnull=True)
                        & models.Q(target_sanctum_details__isnull=True)
                    )
                ),
            ),
            # ---- MANTLE ------------------------------------------------------
            # One active thread per (owner, mantle). Retired threads
            # (retired_at IS NOT NULL) are excluded so a character can retire a
            # mantle thread and later weave a new one on the same mantle.
            models.UniqueConstraint(
                fields=["owner", "target_mantle"],
                condition=models.Q(target_kind=TargetKind.MANTLE, retired_at__isnull=True),
                name="uniq_thread_mantle_active",
            ),
            models.CheckConstraint(
                name="thread_mantle_payload",
                check=(
                    ~models.Q(target_kind=TargetKind.MANTLE)
                    | (
                        models.Q(target_mantle__isnull=False)
                        & models.Q(target_trait__isnull=True)
                        & models.Q(target_technique__isnull=True)
                        & models.Q(target_relationship_track__isnull=True)
                        & models.Q(target_capstone__isnull=True)
                        & models.Q(target_facet__isnull=True)
                        & models.Q(target_covenant_role__isnull=True)
                        & models.Q(target_gift__isnull=True)
                        & models.Q(target_sanctum_details__isnull=True)
                    )
                ),
            ),
            # ---- SANCTUM ------------------------------------------------------
            # Plan 4 §F. SANCTUM threads pay resonance income to woven weavers
            # via the resonance generation cron tick. Each weaver-character may
            # have at most one active PERSONAL_OWN thread (their own home) and
            # one active COVENANT thread (the sacred ground of one covenant they
            # actively belong to). HELPER threads on other personas' personal
            # Sanctums are unlimited; non-SANCTUM threads must not set slot_kind.
            models.UniqueConstraint(
                fields=["owner"],
                condition=models.Q(
                    target_kind=TargetKind.SANCTUM,
                    slot_kind=SanctumSlotKind.PERSONAL_OWN,
                    retired_at__isnull=True,
                ),
                name="uniq_thread_sanctum_personal_own_active",
            ),
            models.UniqueConstraint(
                fields=["owner"],
                condition=models.Q(
                    target_kind=TargetKind.SANCTUM,
                    slot_kind=SanctumSlotKind.COVENANT,
                    retired_at__isnull=True,
                ),
                name="uniq_thread_sanctum_covenant_active",
            ),
            models.UniqueConstraint(
                fields=["owner", "target_sanctum_details"],
                condition=models.Q(
                    target_kind=TargetKind.SANCTUM,
                    retired_at__isnull=True,
                ),
                name="uniq_thread_sanctum_owner_target_active",
            ),
            models.CheckConstraint(
                name="thread_sanctum_payload",
                check=(
                    ~models.Q(target_kind=TargetKind.SANCTUM)
                    | (
                        models.Q(target_sanctum_details__isnull=False)
                        & ~models.Q(slot_kind="")
                        & models.Q(target_trait__isnull=True)
                        & models.Q(target_technique__isnull=True)
                        & models.Q(target_relationship_track__isnull=True)
                        & models.Q(target_capstone__isnull=True)
                        & models.Q(target_facet__isnull=True)
                        & models.Q(target_covenant_role__isnull=True)
                        & models.Q(target_gift__isnull=True)
                        & models.Q(target_mantle__isnull=True)
                    )
                ),
            ),
            models.CheckConstraint(
                name="thread_slot_kind_only_for_sanctum",
                check=(models.Q(target_kind=TargetKind.SANCTUM) | models.Q(slot_kind="")),
            ),
            # ---- signature_bonus: only allowed on TECHNIQUE threads (#1582) ----
            models.CheckConstraint(
                name="thread_signature_bonus_technique_only",
                check=(
                    models.Q(signature_bonus__isnull=True)
                    | models.Q(target_kind=TargetKind.TECHNIQUE)
                ),
            ),
        ]

    def __str__(self) -> str:
        return f"Thread<{self.target_kind}> for {self.owner_id} ({self.resonance_id})"

    @property
    def target(self) -> models.Model | None:
        """Return the populated FK object, picked by target_kind."""
        _kind_to_attr: dict[str, str] = {
            TargetKind.TRAIT: "target_trait",
            TargetKind.TECHNIQUE: "target_technique",
            TargetKind.RELATIONSHIP_TRACK: "target_relationship_track",
            TargetKind.RELATIONSHIP_CAPSTONE: "target_capstone",
            TargetKind.FACET: "target_facet",
            TargetKind.COVENANT_ROLE: "target_covenant_role",
            TargetKind.GIFT: "target_gift",
            TargetKind.MANTLE: "target_mantle",
            TargetKind.SANCTUM: "target_sanctum_details",
        }
        attr = _kind_to_attr.get(self.target_kind)
        return getattr(self, attr) if attr is not None else None

    def clean(self) -> None:
        """Validate exactly-one-target rule.

        DB constraints catch the same shape errors at write time; ``clean()``
        is the user-facing error path (forms / serializers / tests calling
        ``full_clean()``).
        """
        # Map target_kind -> expected_field_name
        kind_to_field: dict[str, str] = {
            TargetKind.TRAIT: "target_trait",
            TargetKind.TECHNIQUE: "target_technique",
            TargetKind.FACET: "target_facet",
            TargetKind.RELATIONSHIP_TRACK: "target_relationship_track",
            TargetKind.RELATIONSHIP_CAPSTONE: "target_capstone",
            TargetKind.COVENANT_ROLE: "target_covenant_role",
            TargetKind.GIFT: "target_gift",
            TargetKind.MANTLE: "target_mantle",
            TargetKind.SANCTUM: "target_sanctum_details",
        }
        all_target_fields = (
            "target_trait",
            "target_technique",
            "target_facet",
            "target_relationship_track",
            "target_capstone",
            "target_covenant_role",
            "target_gift",
            "target_mantle",
            "target_sanctum_details",
        )

        expected_field = kind_to_field.get(self.target_kind)
        if expected_field is None:
            raise ValidationError(
                {"target_kind": f"Unknown target_kind: {self.target_kind!r}."},
            )

        if getattr(self, expected_field) is None:
            raise ValidationError(
                {expected_field: f"target_kind={self.target_kind} requires {expected_field}."},
            )

        for field_name in all_target_fields:
            if field_name == expected_field:
                continue
            if getattr(self, field_name) is not None:
                raise ValidationError(
                    {
                        field_name: (
                            f"target_kind={self.target_kind} requires {field_name} to be null."
                        ),
                    },
                )

        # slot_kind: required for SANCTUM, must be empty for all other targets.
        if self.target_kind == TargetKind.SANCTUM:
            if not self.slot_kind:
                raise ValidationError(
                    {"slot_kind": "SANCTUM target_kind requires slot_kind to be set."},
                )
        elif self.slot_kind:
            raise ValidationError(
                {"slot_kind": f"slot_kind must be empty for target_kind={self.target_kind}."},
            )

        # signature_bonus: only allowed on TECHNIQUE threads (#1582).
        if self.signature_bonus_id is not None and self.target_kind != TargetKind.TECHNIQUE:
            raise ValidationError(
                {
                    "signature_bonus": (
                        "signature_bonus may only be set when target_kind=TECHNIQUE "
                        f"(current target_kind={self.target_kind})."
                    ),
                },
            )


class ThreadLevelUnlock(SharedMemoryModel):
    """Per-thread level-unlock receipt.

    Records that ``thread`` paid ``xp_spent`` to unlock ``unlocked_level`` on the
    internal level scale (multiples of 10). Spec A §2.1 lines 200-206. Pairs
    with ThreadXPLockedLevel (the global price list); a row here represents one
    ownership instance of one boundary on one thread.
    """

    thread = models.ForeignKey(
        Thread,
        on_delete=models.PROTECT,
        related_name="level_unlocks",
        help_text="Thread that purchased this level unlock.",
    )
    unlocked_level = models.PositiveSmallIntegerField(
        help_text="Level boundary unlocked (matches ThreadXPLockedLevel.level).",
    )
    xp_spent = models.PositiveIntegerField(
        help_text="XP actually spent at unlock time (snapshot of price list).",
    )
    acquired_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (("thread", "unlocked_level"),)
        ordering = ("thread", "unlocked_level")

    def __str__(self) -> str:
        return f"Thread {self.thread_id} -> lvl {self.unlocked_level}"
