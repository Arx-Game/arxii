"""Threads and thread-pull infrastructure.

Per-character Thread rows anchored to a trait/technique/item/room/relationship.
ThreadLevelUnlock is the per-thread XP-locked-boundary receipt.
ThreadPullCost is the per-tier pull-cost tuning table.
ThreadXPLockedLevel is the XP-locked boundary price list.
ThreadPullEffect is the authored pull-effect template.
"""

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import models
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper.models import SharedMemoryModel

from world.magic.constants import (
    THREADWEAVING_ITEM_TYPECLASSES,
    EffectKind,
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
    """

    tier = models.PositiveSmallIntegerField(unique=True)
    resonance_cost = models.PositiveSmallIntegerField()
    anima_per_thread = models.PositiveSmallIntegerField()
    label = models.CharField(max_length=32)

    class Meta:
        ordering = ("tier",)

    def __str__(self) -> str:
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

    class Meta:
        indexes = [
            models.Index(fields=["target_kind", "resonance", "tier"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["target_kind", "resonance", "tier", "min_thread_level"],
                name="threadpulleffect_lookup_key",
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
                    )
                ),
                name="threadpulleffect_narrative_only_payload",
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
        }
        validator = validators.get(self.effect_kind)
        if validator is not None:
            validator(numeric_fields)

    def _clean_flat_bonus(self, numeric_fields: dict[str, int | None]) -> None:
        self._require_only("flat_bonus_amount", numeric_fields, self.capability_grant)

    def _clean_intensity_bump(self, numeric_fields: dict[str, int | None]) -> None:
        self._require_only("intensity_bump_amount", numeric_fields, self.capability_grant)

    def _clean_vital_bonus(self, numeric_fields: dict[str, int | None]) -> None:
        self._require_only("vital_bonus_amount", numeric_fields, self.capability_grant)
        if not self.vital_target:
            raise ValidationError({"vital_target": "VITAL_BONUS requires vital_target."})

    def _clean_capability_grant(self, numeric_fields: dict[str, int | None]) -> None:
        if self.capability_grant is None:
            raise ValidationError(
                {"capability_grant": "CAPABILITY_GRANT requires capability_grant."}
            )
        for name, val in numeric_fields.items():
            if val is not None:
                raise ValidationError({name: "Must be null for CAPABILITY_GRANT."})

    def _clean_narrative_only(self, numeric_fields: dict[str, int | None]) -> None:
        if not self.narrative_snippet.strip():
            raise ValidationError({"narrative_snippet": "NARRATIVE_ONLY requires snippet."})
        if self.capability_grant is not None:
            raise ValidationError({"capability_grant": "Must be null for NARRATIVE_ONLY."})
        for name, val in numeric_fields.items():
            if val is not None:
                raise ValidationError({name: "Must be null for NARRATIVE_ONLY."})

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


class Thread(SharedMemoryModel):
    """Per-character thread anchored to a trait/technique/item/room/relationship.

    Discriminator + typed-FK pattern (Spec A §2.1 lines 83-151). Exactly one
    target_* column is populated, matching ``target_kind``. Three layers of
    enforcement:

    - ``clean()`` raises ValidationError on missing / mismatched targets and on
      ITEM-kind targets whose typeclass isn't in THREADWEAVING_ITEM_TYPECLASSES.
    - Per-kind CheckConstraints mirror the "exactly one target_* set, matching
      target_kind" rule at the DB layer (so misuse via .objects.create() also
      fails).
    - Per-kind partial UniqueConstraints prevent duplicate threads within the
      same (owner, resonance, target_kind, target_*) combination, while still
      allowing — for example — an ITEM thread and a ROOM thread on the same
      ObjectDB.
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
    target_object = models.ForeignKey(
        ObjectDB,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="anchored_threads",
        help_text="Set when target_kind in (ITEM, ROOM); null otherwise.",
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
                fields=["owner", "resonance", "target_object"],
                condition=models.Q(target_kind=TargetKind.ITEM),
                name="uniq_thread_item",
            ),
            models.UniqueConstraint(
                fields=["owner", "resonance", "target_object"],
                condition=models.Q(target_kind=TargetKind.ROOM),
                name="uniq_thread_room",
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
                        & models.Q(target_object__isnull=True)
                        & models.Q(target_relationship_track__isnull=True)
                        & models.Q(target_capstone__isnull=True)
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
                        & models.Q(target_object__isnull=True)
                        & models.Q(target_relationship_track__isnull=True)
                        & models.Q(target_capstone__isnull=True)
                    )
                ),
            ),
            models.CheckConstraint(
                name="thread_item_payload",
                check=(
                    ~models.Q(target_kind=TargetKind.ITEM)
                    | (
                        models.Q(target_trait__isnull=True)
                        & models.Q(target_technique__isnull=True)
                        & models.Q(target_object__isnull=False)
                        & models.Q(target_relationship_track__isnull=True)
                        & models.Q(target_capstone__isnull=True)
                    )
                ),
            ),
            models.CheckConstraint(
                name="thread_room_payload",
                check=(
                    ~models.Q(target_kind=TargetKind.ROOM)
                    | (
                        models.Q(target_trait__isnull=True)
                        & models.Q(target_technique__isnull=True)
                        & models.Q(target_object__isnull=False)
                        & models.Q(target_relationship_track__isnull=True)
                        & models.Q(target_capstone__isnull=True)
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
                        & models.Q(target_object__isnull=True)
                        & models.Q(target_relationship_track__isnull=False)
                        & models.Q(target_capstone__isnull=True)
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
                        & models.Q(target_object__isnull=True)
                        & models.Q(target_relationship_track__isnull=True)
                        & models.Q(target_capstone__isnull=False)
                    )
                ),
            ),
        ]

    def __str__(self) -> str:
        return f"Thread<{self.target_kind}> for {self.owner_id} ({self.resonance_id})"

    @property
    def target(self) -> models.Model | None:
        """Return the populated FK object, picked by target_kind."""
        match self.target_kind:
            case TargetKind.TRAIT:
                return self.target_trait
            case TargetKind.TECHNIQUE:
                return self.target_technique
            case TargetKind.ITEM | TargetKind.ROOM:
                return self.target_object
            case TargetKind.RELATIONSHIP_TRACK:
                return self.target_relationship_track
            case TargetKind.RELATIONSHIP_CAPSTONE:
                return self.target_capstone
        return None

    def clean(self) -> None:
        """Validate exactly-one-target rule + ITEM typeclass registry membership.

        DB constraints catch the same shape errors at write time; ``clean()``
        is the user-facing error path (forms / serializers / tests calling
        ``full_clean()``).
        """
        # Map target_kind -> (expected_field_name, list_of_other_field_names)
        kind_to_field: dict[str, str] = {
            TargetKind.TRAIT: "target_trait",
            TargetKind.TECHNIQUE: "target_technique",
            TargetKind.ITEM: "target_object",
            TargetKind.ROOM: "target_object",
            TargetKind.RELATIONSHIP_TRACK: "target_relationship_track",
            TargetKind.RELATIONSHIP_CAPSTONE: "target_capstone",
        }
        all_target_fields = (
            "target_trait",
            "target_technique",
            "target_object",
            "target_relationship_track",
            "target_capstone",
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

        # ITEM-kind: validate the target_object's typeclass is in the
        # THREADWEAVING_ITEM_TYPECLASSES registry (subclass-aware).
        if self.target_kind == TargetKind.ITEM:
            from world.magic.services import _typeclass_path_in_registry  # noqa: PLC0415

            tc_path = self.target_object.db_typeclass_path
            if not _typeclass_path_in_registry(tc_path, THREADWEAVING_ITEM_TYPECLASSES):
                raise ValidationError(
                    {
                        "target_object": (
                            f"Typeclass {tc_path!r} is not in "
                            "THREADWEAVING_ITEM_TYPECLASSES registry."
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
