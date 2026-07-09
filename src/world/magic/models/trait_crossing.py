"""Models for TRAIT thread crossing player choices (#1989).

When a TRAIT thread crosses a PathStage threshold (level 3, 6, 11, 16, 21),
the player chooses a resonance-flavored expression of their stat from an
authored menu (TraitCrossingOption). The choice is recorded as an irreversible
receipt (TraitCrossingChoice) whose payload is read by the extended passive
read paths on CharacterThreadHandler.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.magic.constants import EffectKind, VitalBonusTarget

# Effect kinds valid for trait crossing options.
_TRAIT_CROSSING_EFFECT_KINDS = frozenset(
    {
        EffectKind.FLAT_BONUS,
        EffectKind.VITAL_BONUS,
        EffectKind.CAPABILITY_GRANT,
        EffectKind.NARRATIVE_ONLY,
    }
)


class TraitCrossingOption(SharedMemoryModel):
    """Authored catalog of resonance-flavored stat expressions.

    Staff author one row per (resonance, crossing_level, name). Each row
    defines an effect the player can choose when their TRAIT thread crosses
    that level. The payload columns mirror ThreadPullEffect's shape —
    mutually exclusive per effect_kind, validated by clean().
    """

    resonance = models.ForeignKey(
        "magic.Resonance",
        on_delete=models.PROTECT,
        related_name="trait_crossing_options",
    )
    crossing_level = models.PositiveSmallIntegerField(
        help_text="PathStage crossing level (3, 6, 11, 16, 21).",
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    effect_kind = models.CharField(
        max_length=32,
        choices=EffectKind.choices,
    )
    flat_bonus_amount = models.SmallIntegerField(null=True, blank=True)
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
        related_name="trait_crossing_options",
    )
    narrative_snippet = models.TextField(blank=True)
    is_default = models.BooleanField(
        default=False,
        help_text=(
            "When a thread skips this crossing (multi-crossing imbue), "
            "this option is picked automatically. One per "
            "(resonance, crossing_level)."
        ),
    )
    discovery_achievement = models.ForeignKey(
        "achievements.Achievement",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="trait_crossing_options",
    )
    codex_entry = models.ForeignKey(
        "codex.CodexEntry",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="trait_crossing_options",
    )

    class Meta:
        unique_together: list[str] = [["resonance", "crossing_level", "name"]]
        ordering: list[str] = ["resonance", "crossing_level", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["resonance", "crossing_level"],
                condition=models.Q(is_default=True),
                name="one_default_trait_crossing_option",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} (L{self.crossing_level} {self.resonance})"

    def clean(self) -> None:
        """Validate payload/effect_kind shape — mirrors ThreadPullEffect.clean()."""
        super().clean()
        if self.effect_kind not in _TRAIT_CROSSING_EFFECT_KINDS:
            allowed = ", ".join(sorted(_TRAIT_CROSSING_EFFECT_KINDS))
            msg = f"effect_kind must be one of: {allowed} for trait crossing options."
            raise ValidationError({"effect_kind": msg})

        numeric_fields: dict[str, int | None] = {
            "flat_bonus_amount": self.flat_bonus_amount,
            "vital_bonus_amount": self.vital_bonus_amount,
        }
        validators = {
            EffectKind.FLAT_BONUS: self._clean_flat_bonus,
            EffectKind.VITAL_BONUS: self._clean_vital_bonus,
            EffectKind.CAPABILITY_GRANT: self._clean_capability_grant,
            EffectKind.NARRATIVE_ONLY: self._clean_narrative_only,
        }
        validator = validators.get(self.effect_kind)
        if validator is not None:
            validator(numeric_fields)

    def _clean_flat_bonus(self, numeric_fields: dict[str, int | None]) -> None:  # noqa: ARG002
        if self.flat_bonus_amount is None:
            raise ValidationError({"flat_bonus_amount": "Required for FLAT_BONUS."})
        if self.vital_bonus_amount is not None:
            raise ValidationError({"vital_bonus_amount": "Must be null for FLAT_BONUS."})
        if self.vital_target:
            raise ValidationError({"vital_target": "Must be null for FLAT_BONUS."})
        if self.capability_grant is not None:
            raise ValidationError({"capability_grant": "Must be null for FLAT_BONUS."})

    def _clean_vital_bonus(self, numeric_fields: dict[str, int | None]) -> None:  # noqa: ARG002
        if self.vital_bonus_amount is None:
            raise ValidationError({"vital_bonus_amount": "Required for VITAL_BONUS."})
        if not self.vital_target:
            raise ValidationError({"vital_target": "Required for VITAL_BONUS."})
        if self.flat_bonus_amount is not None:
            raise ValidationError({"flat_bonus_amount": "Must be null for VITAL_BONUS."})
        if self.capability_grant is not None:
            raise ValidationError({"capability_grant": "Must be null for VITAL_BONUS."})

    def _clean_capability_grant(self, numeric_fields: dict[str, int | None]) -> None:
        if self.capability_grant is None:
            raise ValidationError({"capability_grant": "Required for CAPABILITY_GRANT."})
        for name, val in numeric_fields.items():
            if val is not None:
                raise ValidationError({name: "Must be null for CAPABILITY_GRANT."})
        if self.vital_target:
            raise ValidationError({"vital_target": "Must be null for CAPABILITY_GRANT."})

    def _clean_narrative_only(self, numeric_fields: dict[str, int | None]) -> None:
        if not self.narrative_snippet.strip():
            raise ValidationError({"narrative_snippet": "Required for NARRATIVE_ONLY."})
        if self.capability_grant is not None:
            raise ValidationError({"capability_grant": "Must be null for NARRATIVE_ONLY."})
        for name, val in numeric_fields.items():
            if val is not None:
                raise ValidationError({name: "Must be null for NARRATIVE_ONLY."})
        if self.vital_target:
            raise ValidationError({"vital_target": "Must be null for NARRATIVE_ONLY."})


class TraitCrossingChoice(SharedMemoryModel):
    """Irreversible per-thread receipt of a player's crossing choice.

    The choice IS the effect record — the read paths on CharacterThreadHandler
    traverse ``choice.option`` to read the payload columns. No ThreadPullEffect
    row is written (avoids UniqueConstraint collision + SharedMemoryModel
    cache pollution on the lookup table).
    """

    thread = models.ForeignKey(
        "magic.Thread",
        on_delete=models.CASCADE,
        related_name="crossing_choices",
    )
    crossing_level = models.PositiveSmallIntegerField(
        help_text="PathStage crossing level (3, 6, 11, 16, 21).",
    )
    option = models.ForeignKey(
        TraitCrossingOption,
        on_delete=models.PROTECT,
        related_name="choices",
    )
    chosen_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["thread", "crossing_level"],
                name="one_choice_per_thread_per_crossing",
            ),
        ]
        ordering = ["-chosen_at"]

    def __str__(self) -> str:
        return f"Choice(thread={self.thread_id}, L{self.crossing_level}, opt={self.option_id})"


class PendingTraitCrossingOffer(SharedMemoryModel):
    """Poll-able offer created when a TRAIT thread crosses a threshold.

    Created by TraitCrossingHandler; resolved by the player picking an option
    via ResolveTraitCrossingOfferAction (telnet or web). One pending offer per
    thread at a time.
    """

    thread = models.ForeignKey(
        "magic.Thread",
        on_delete=models.CASCADE,
        related_name="pending_crossing_offers",
    )
    crossing_level = models.PositiveSmallIntegerField(
        help_text="PathStage crossing level (3, 6, 11, 16, 21).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["thread"],
                name="one_pending_trait_crossing_per_thread",
            ),
        ]

    def __str__(self) -> str:
        return f"PendingTraitCrossingOffer(thread={self.thread_id}, L{self.crossing_level})"
