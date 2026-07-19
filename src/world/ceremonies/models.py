"""Ceremony framework models (#2289).

A ceremony is lightly-structured freeform RP: commands bookend the scene (open,
offering, speech, finish/abandon) while poses carry it. Ceremonies consume the
worship primitive (#2355) and point into events/scenes — never the reverse
(ADR-0010). Spec Decisions 10–13 (issue #2289 body) govern the being/presented
mapping, the devotion economy, bounded abandonment, and retired honorees.
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.ceremonies.constants import CeremonyStatus, CeremonyTypeKey, SeanceOfferStatus


class CeremonyType(SharedMemoryModel):
    """A data-driven kind of ceremony (Funeral, Blessing, Sermon; later Wedding…)."""

    key = models.CharField(max_length=20, choices=CeremonyTypeKey.choices, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(
        blank=True, help_text="PLACEHOLDER player-facing copy — Apostate rewrite pending."
    )

    class Meta:
        ordering = ["key"]

    def __str__(self) -> str:
        return self.name


class Ceremony(SharedMemoryModel):
    """One performed ceremony instance.

    ``being`` is the TRUE recipient of the worship; ``presented_being`` is what
    attendees see. They differ only in the twisted-rite case (Decision 10) and
    player-facing surfaces must render ``presented_being`` only.
    """

    ceremony_type = models.ForeignKey(
        CeremonyType, on_delete=models.PROTECT, related_name="ceremonies"
    )
    officiant = models.ForeignKey(
        "scenes.Persona", on_delete=models.PROTECT, related_name="ceremonies_officiated"
    )
    being = models.ForeignKey(
        "worship.WorshippedBeing", on_delete=models.PROTECT, related_name="ceremonies"
    )
    presented_being = models.ForeignKey(
        "worship.WorshippedBeing", on_delete=models.PROTECT, related_name="+"
    )
    location = models.ForeignKey(
        "evennia_extensions.RoomProfile", on_delete=models.PROTECT, related_name="ceremonies"
    )
    scene = models.ForeignKey(
        "scenes.Scene",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ceremonies",
    )
    event = models.ForeignKey(
        "events.Event",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ceremonies",
    )
    status = models.CharField(
        max_length=20, choices=CeremonyStatus.choices, default=CeremonyStatus.OPEN
    )
    opened_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    quality_level = models.IntegerField(
        null=True,
        blank=True,
        help_text="Success level of the officiant's Rites roll at finish (null until then).",
    )

    class Meta:
        ordering = ["-opened_at"]
        verbose_name_plural = "Ceremonies"
        constraints = [
            models.UniqueConstraint(
                fields=["location"],
                condition=models.Q(status="open"),
                name="one_open_ceremony_per_location",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.ceremony_type} at {self.location} ({self.status})"

    @property
    def is_twisted(self) -> bool:
        """True when the rite secretly serves a different being than presented."""
        return self.being_id != self.presented_being_id


class CeremonyHonoree(SharedMemoryModel):
    """A character recognized by the ceremony (the deceased at a funeral)."""

    ceremony = models.ForeignKey(Ceremony, on_delete=models.CASCADE, related_name="honorees")
    honoree_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.PROTECT,
        related_name="ceremony_honors",
    )
    prestige_awarded = models.BigIntegerField(default=0)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["ceremony", "honoree_sheet"], name="unique_ceremony_honoree"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.honoree_sheet} honored at {self.ceremony}"


class CeremonyOffering(SharedMemoryModel):
    """An item sacrificed during the ceremony (the item itself is destroyed)."""

    ceremony = models.ForeignKey(Ceremony, on_delete=models.CASCADE, related_name="offerings")
    item_name = models.CharField(max_length=200)
    item_value = models.PositiveIntegerField(default=0)
    item_legend_value = models.PositiveIntegerField(
        default=0,
        help_text="Legend value of the offered item at sacrifice time (#2359).",
    )
    worship_grant = models.ForeignKey(
        "worship.WorshipGrant",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    offered_by = models.ForeignKey(
        "scenes.Persona", on_delete=models.PROTECT, related_name="ceremony_offerings"
    )

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.item_name} offered at {self.ceremony}"


class CeremonySpeech(SharedMemoryModel):
    """A recognized speech; the speaker's Oratory roll shapes honoree prestige."""

    ceremony = models.ForeignKey(Ceremony, on_delete=models.CASCADE, related_name="speeches")
    speaker = models.ForeignKey(
        "scenes.Persona", on_delete=models.PROTECT, related_name="ceremony_speeches"
    )
    success_level = models.IntegerField(
        null=True, blank=True, help_text="Speech check success level (null if unrolled)."
    )
    target_honoree = models.ForeignKey(
        CeremonyHonoree,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="speeches",
        help_text="Speech dedicated to one honoree; null = all honorees.",
    )

    class Meta:
        ordering = ["id"]
        verbose_name_plural = "Ceremony speeches"

    def __str__(self) -> str:
        return f"Speech by {self.speaker} at {self.ceremony}"


class CeremonyConfig(SharedMemoryModel):
    """Staff-tunable singleton for ceremony magnitudes — ALL PLACEHOLDER values.

    Access via ``get_ceremony_config()`` (singleton-by-convention, mirrors
    ``ResonanceGainConfig``).
    """

    officiant_cut_percent = models.PositiveIntegerField(
        default=20, help_text="Officiant's prestige cut as % of the honoree award."
    )
    offering_resonance_per_value = models.PositiveIntegerField(
        default=1, help_text="Worship resonance granted per point of offered item value."
    )
    offering_prestige_per_value = models.PositiveIntegerField(
        default=1, help_text="Honoree prestige per point of offered item value."
    )
    speech_prestige_base = models.PositiveIntegerField(
        default=10, help_text="Base honoree prestige per successful speech level."
    )
    base_honoree_prestige = models.PositiveIntegerField(
        default=50, help_text="Base prestige deed value per honoree at finish."
    )
    quality_multiplier_percent_per_level = models.PositiveIntegerField(
        default=25, help_text="Tally multiplier % added per quality success level."
    )
    leak_detect_difficulty = models.PositiveIntegerField(
        default=30, help_text="Perception difficulty for sensing a twisted rite."
    )
    devotion_per_offering = models.PositiveIntegerField(
        default=5, help_text="Devotion favor an offerer gains per offering."
    )
    devotion_officiant = models.PositiveIntegerField(
        default=10, help_text="Devotion favor the officiant gains at finish."
    )

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"CeremonyConfig (pk={self.pk})"


def get_ceremony_config() -> CeremonyConfig:
    """Get-or-create the first CeremonyConfig row (singleton-by-convention)."""
    config = CeremonyConfig.objects.first()
    if config is None:
        config = CeremonyConfig.objects.create()
    return config


class SeanceManifestationOffer(SharedMemoryModel):
    """Consent gate for a Seance honoree's voice/puppet grant (#2393).

    One row per CeremonyHonoree on a Seance-type ceremony, created when the
    ceremony opens. PENDING until the honoree's own controlling account
    answers (see world.ceremonies.services.respond_to_seance_offer) — accept
    both widens GhostWindowPrerequisite's third container AND, for a retired
    honoree, unlocks the narrow puppet-grant fallback in
    Account.can_puppet_for_seance. Never mutated once ACCEPTED/DECLINED; a
    fresh ceremony mints a fresh row (this one just becomes unreachable —
    every consumer filters on `ceremony_honoree__ceremony__status=OPEN`).
    """

    ceremony_honoree = models.OneToOneField(
        CeremonyHonoree, on_delete=models.CASCADE, related_name="seance_offer"
    )
    status = models.CharField(
        max_length=20, choices=SeanceOfferStatus.choices, default=SeanceOfferStatus.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Seance offer for {self.ceremony_honoree} ({self.status})"
