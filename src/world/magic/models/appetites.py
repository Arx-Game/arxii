"""Appetite economy models (#2853): upkeep configs, receipts, and the feeding ledger.

Appetites are anchored on tag-identified Distinctions (the ADR-0179 pattern —
``appetite-blood`` / ``appetite-essence``); these models carry the periodic
anima upkeep some appetite tiers pay (vampires weekly, shades daily) and the
audit trail of every feeding. The upkeep shape deliberately mirrors the
Somehow Always Broke purse drain (``currency.DistinctionPurseDrain`` +
``PurseDrainWeek``): a config row keyed on the Distinction, per-period receipt
rows for idempotency, DRAIN-phased crons.
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

_CHARACTER_SHEET_FK = "character_sheets.CharacterSheet"


class AppetitePeriod(models.TextChoices):
    """How often an appetite upkeep drain fires."""

    DAILY = "daily", "Daily"
    WEEKLY = "weekly", "Weekly"


class AppetiteUpkeep(SharedMemoryModel):
    """Authored periodic anima drain for holders of an appetite Distinction (#2853).

    Vampire: weekly 1, floor 10% of maximum. Shade: daily 1, floor 0.
    ``floor_percent`` is the fraction of ``CharacterAnima.maximum`` the drain
    never takes ``current`` below — starvation dims, it never kills.
    Magnitudes are a PLACEHOLDER author pass.
    """

    distinction = models.OneToOneField(
        "distinctions.Distinction",
        on_delete=models.CASCADE,
        related_name="appetite_upkeep",
        help_text="Holders of this distinction pay the drain.",
    )
    period = models.CharField(max_length=10, choices=AppetitePeriod.choices)
    amount = models.PositiveIntegerField(
        default=1,
        help_text="Anima drained per period.",
    )
    floor_percent = models.PositiveIntegerField(
        default=0,
        help_text="Percent of maximum the drain never takes current below.",
    )

    class Meta:
        verbose_name = "Appetite Upkeep"
        verbose_name_plural = "Appetite Upkeeps"

    def __str__(self) -> str:
        floor = self.floor_percent
        return f"{self.distinction.name}: -{self.amount} {self.period} (floor {floor}%)"


class AppetiteUpkeepReceipt(SharedMemoryModel):
    """Per-holder-per-period idempotency receipt for an appetite drain (#2853).

    ``period_start`` is the calendar date the period began (the drain date for
    DAILY; the anchored week start for WEEKLY) — a rerun of the cron inside the
    same period finds the receipt and skips.
    """

    character_sheet = models.ForeignKey(
        _CHARACTER_SHEET_FK,
        on_delete=models.CASCADE,
        related_name="appetite_upkeep_receipts",
    )
    upkeep = models.ForeignKey(
        AppetiteUpkeep,
        on_delete=models.CASCADE,
        related_name="receipts",
    )
    period_start = models.DateField()
    drained = models.PositiveIntegerField(
        default=0,
        help_text="Anima actually removed (0 when already at/below the floor).",
    )
    drained_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Appetite Upkeep Receipt"
        verbose_name_plural = "Appetite Upkeep Receipts"
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet", "upkeep", "period_start"],
                name="unique_appetite_upkeep_receipt_per_period",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.character_sheet} {self.upkeep} @ {self.period_start} (-{self.drained})"


class FeedingRecord(SharedMemoryModel):
    """Audit row for one feeding: who drained whom, how, and what it cost (#2853).

    Mirrors the Sineating audit shape (the other two-party anima transfer).
    ``was_lethal`` marks a feed that routed the victim into the death pipeline.
    """

    feeder_sheet = models.ForeignKey(
        _CHARACTER_SHEET_FK,
        on_delete=models.CASCADE,
        related_name="feedings_taken",
    )
    victim_sheet = models.ForeignKey(
        _CHARACTER_SHEET_FK,
        on_delete=models.CASCADE,
        related_name="feedings_suffered",
    )
    scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feedings",
    )
    amount_mode = models.CharField(
        max_length=10,
        help_text="SIP / DRINK / GORGE as fed (post any lost-control escalation).",
    )
    lost_control = models.BooleanField(
        default=False,
        help_text="A restraint check failed and escalated the feed to GORGE.",
    )
    anima_taken = models.PositiveIntegerField(default=0)
    glut_gained = models.PositiveIntegerField(
        default=0,
        help_text="Portion of the take that landed as overfill glut.",
    )
    victim_fatigue = models.PositiveIntegerField(
        default=0,
        help_text="Fatigue applied to the victim from the anima loss.",
    )
    was_lethal = models.BooleanField(default=False)
    fed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fed_at"]
        verbose_name = "Feeding Record"
        verbose_name_plural = "Feeding Records"

    def __str__(self) -> str:
        return f"{self.feeder_sheet} fed on {self.victim_sheet} ({self.amount_mode})"
