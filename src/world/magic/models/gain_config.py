"""Resonance gain tuning config singleton (Spec C §2.1)."""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class ResonanceGainConfig(SharedMemoryModel):
    """Staff-tunable singleton for resonance gain magnitudes.

    One row per environment. Access via ``get_resonance_gain_config()`` —
    singleton-by-convention, no DB-level uniqueness constraint.
    """

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
