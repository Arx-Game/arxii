"""Predator ecology models (#3093): named antagonists on a slow menace ladder.

Predator bands are deliberately a THIN, dedicated model — never Organizations
(Apostate's ruling: orgs are the player-holding construct; pure antagonists
take no members, so they carry none of that structure). Being rows here still
buys tidings, spy targeting, crisis attribution, and history.
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.predators.constants import MenaceStage


class PredatorKind(NaturalKeyMixin, SharedMemoryModel):
    """Authored predator vocabulary: bandit company, pirate fleet, raider warband."""

    name = models.CharField(max_length=60, unique=True)
    description = models.TextField(
        blank=True,
        help_text="PLACEHOLDER flavor pending the content pass.",
    )
    base_strength = models.PositiveSmallIntegerField(
        default=100,
        help_text="Starting strength for a freshly spawned band of this kind.",
    )
    weeks_per_stage_override = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Optional pacing override applied to EVERY stage; null = ladder defaults.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class PredatorBand(SharedMemoryModel):
    """A named antagonist working its way up the menace ladder (#3093).

    Bands fixate on the weakest-PERCEIVED landed org in reach (honoring
    consort-derived regional peace) and advance one small stage at a time,
    only while unanswered — roughly ten weekly crons separate first rumor
    from an actual raid. Counterplay knocks them down, burns strength, and
    can break them entirely.
    """

    name = models.CharField(max_length=80, unique=True)
    kind = models.ForeignKey(
        PredatorKind,
        on_delete=models.PROTECT,
        related_name="bands",
    )
    home_region = models.ForeignKey(
        "arxii.Area",
        on_delete=models.PROTECT,
        related_name="predator_bands",
        help_text="Anchors reach (prey selection) and the regional-peace scope.",
    )
    strength = models.PositiveSmallIntegerField(
        default=100,
        help_text="Burned by counterplay; dormancy below the floor, disbanded at zero.",
    )
    loot_stash = models.PositiveBigIntegerField(
        default=0,
        help_text="Coppers skimmed and looted — bounty flavor when the band is broken.",
    )
    prey = models.ForeignKey(
        "arxii.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stalking_predators",
        help_text="The landed org this band currently menaces.",
    )
    stage = models.CharField(
        max_length=20,
        choices=MenaceStage.choices,
        default=MenaceStage.RUMORS,
    )
    weeks_unanswered = models.PositiveSmallIntegerField(
        default=0,
        help_text="Weeks at the current stage with no counterplay; drives advancement.",
    )
    stage_entered_at = models.DateTimeField(auto_now_add=True)
    dormant_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text="A mauled band licks its wounds; null = active.",
    )
    disbanded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        state = "disbanded" if self.disbanded_at else self.get_stage_display()
        return f"{self.name} ({state})"

    @property
    def is_active(self) -> bool:
        from django.utils import timezone  # noqa: PLC0415

        if self.disbanded_at is not None:
            return False
        return self.dormant_until is None or self.dormant_until <= timezone.now()


class MenaceEvent(SharedMemoryModel):
    """One step of a band's story (#3093) — the tidings source and the history.

    Every stage transition (up or down) emits one, so the two-month build-up
    is a story the whole region watches in the feeds.
    """

    band = models.ForeignKey(
        PredatorBand,
        on_delete=models.CASCADE,
        related_name="events",
    )
    stage = models.CharField(max_length=20, choices=MenaceStage.choices)
    escalated = models.BooleanField(
        default=True,
        help_text="True when the band rose to this stage; False when knocked down to it.",
    )
    headline = models.CharField(
        max_length=200,
        help_text="PLACEHOLDER feed line pending the content pass.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.band.name}: {self.headline}"


class AfflictionSign(SharedMemoryModel):
    """The week of dread before an Affliction outbreak (#3093).

    Signs surface as warning tidings with zero mechanical effect; an
    unconverted sign becomes the open (deterrence-blind) crisis on the next
    weekly tick. Small steps, always announced.
    """

    domain = models.ForeignKey(
        "arxii.Domain",
        on_delete=models.CASCADE,
        related_name="affliction_signs",
    )
    crisis_type = models.ForeignKey(
        "arxii.DomainCrisisType",
        on_delete=models.CASCADE,
        related_name="signs",
    )
    converted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the sign became an open crisis; null = still only dread.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        state = "converted" if self.converted_at else "looming"
        return f"{self.crisis_type} signs at {self.domain} ({state})"
