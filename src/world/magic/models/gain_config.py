"""Resonance gain tuning config singleton (Spec C §2.1)."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from core.managers import ArxSharedMemoryManager
from core.models import ArxSharedMemoryModel as SharedMemoryModel
from world.traits.constants import TraitType


class ResonanceGainConfig(SharedMemoryModel):
    """Staff-tunable singleton for resonance gain magnitudes.

    One row per environment. Access via ``get_resonance_gain_config()`` —
    singleton-by-convention, no DB-level uniqueness constraint.
    """

    objects = ArxSharedMemoryManager()

    weekly_pot_per_character = models.PositiveIntegerField(
        default=20,
        help_text="Weekly resonance pot each endorser distributes across their "
        "pose endorsements at settlement.",
    )
    scene_entry_grant = models.PositiveIntegerField(
        default=4,
        help_text="Flat grant per scene-entry endorsement.",
    )
    residence_daily_trickle_per_resonance = models.PositiveIntegerField(
        default=1,
        help_text="Daily trickle per matching (residence-tagged, character-claimed) resonance.",
    )
    outfit_daily_trickle_per_item_resonance = models.PositiveIntegerField(
        default=1,
        help_text="Daily trickle per worn resonance-tagged item (unused until Items system ships).",
    )
    same_pair_daily_cap = models.PositiveIntegerField(
        default=0,
        help_text="Max endorsements from same endorser -> same endorsee per "
        "rolling 24h. 0 disables the cap.",
    )
    settlement_day_of_week = models.IntegerField(
        default=0,
        help_text="ISO weekday (Monday=0) for the weekly pose-endorsement settlement tick cue.",
    )
    entry_flourish_grant = models.PositiveIntegerField(
        default=10,
        help_text=(
            "Flat resonance grant awarded to a character when they perform a "
            "successful entry flourish (Entrance action with resonance declared)."
        ),
    )
    style_presentation_grant = models.PositiveIntegerField(
        default=4,
        help_text="Flat grant per style-presentation endorsement (#1152).",
    )
    bonus_check_type = models.ForeignKey(
        "arxii.CheckType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "The check rolled once per affinity on every earned resonance gain, and once per "
            "pull or kindled cast. It must weigh exactly one stat. The act's own stat "
            "replaces it and the affinity's skill is added. Blank turns the bonus check off: "
            "every gain pays its plain amount and every pull is worth 100 percent."
        ),
    )
    bonus_difficulty_level = models.PositiveSmallIntegerField(
        default=0,
        db_default=0,
        help_text=(
            "Difficulty of the bonus check. Authored as a level (0 = no difficulty): the "
            "roll meets that level's baseline."
        ),
    )

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        "accounts.AccountDB",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resonance_gain_config_edits",
    )

    def __str__(self) -> str:
        return f"ResonanceGainConfig (pk={self.pk})"

    def clean(self) -> None:
        """The bonus check weighs exactly one stat, so the act's own stat can replace it."""
        super().clean()
        if self.bonus_check_type_id is None:
            return
        stat_weights = [
            ctt
            for ctt in self.bonus_check_type.traits.all()
            if ctt.trait.trait_type == TraitType.STAT
        ]
        if len(stat_weights) != 1:
            raise ValidationError(
                {
                    "bonus_check_type": (
                        "The bonus check must weigh exactly one stat, so the stat of the "
                        "act being rewarded can stand in for it."
                    )
                }
            )
