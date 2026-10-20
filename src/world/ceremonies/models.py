"""Ceremony framework models (#2289).

A ceremony is lightly-structured freeform RP: commands bookend the scene (open,
offering, speech, finish/abandon) while poses carry it. Ceremonies consume the
worship primitive (#2355) and point into events/scenes — never the reverse
(ADR-0010). Spec Decisions 10–13 (issue #2289 body) govern the being/presented
mapping, the devotion economy, bounded abandonment, and retired honorees.
"""

from django.db import models

from core.models import ArxSharedMemoryModel as SharedMemoryModel
from world.ceremonies.constants import (
    CeremonyStatus,
    CeremonyTypeKey,
    ConversionOfferStatus,
    SeanceOfferStatus,
)
from world.items.constants import MeaningSignalKind

_PERSONA_MODEL = "arxii.Persona"


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
        _PERSONA_MODEL, on_delete=models.PROTECT, related_name="ceremonies_officiated"
    )
    being = models.ForeignKey(
        "arxii.WorshippedBeing", on_delete=models.PROTECT, related_name="ceremonies"
    )
    presented_being = models.ForeignKey(
        "arxii.WorshippedBeing", on_delete=models.PROTECT, related_name="+"
    )
    location = models.ForeignKey(
        "arxii.RoomProfile", on_delete=models.PROTECT, related_name="ceremonies"
    )
    scene = models.ForeignKey(
        "arxii.Scene",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ceremonies",
    )
    event = models.ForeignKey(
        "arxii.Event",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ceremonies",
    )
    title = models.ForeignKey(
        "arxii.Title",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="coronation_ceremonies",
        help_text="CORONATION only: the already-held title being solemnized (#2358).",
    )
    worship_rite = models.ForeignKey(
        "arxii.WorshipRite",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ceremonies",
        help_text=(
            "A tier 3 rite this ceremony performs (#3777): at finish the officiant's Rites "
            "roll pays the rite's tier award on top of the ceremony's own honors."
        ),
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
        "arxii.CharacterSheet",
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
    """An item sacrificed to a being (the item itself is destroyed).

    Either during a ceremony (``ceremony`` set) or, since #4333 slice 2, as a
    sacrifice at the being's shrine or temple outside one (``being`` set, with
    the sacrificer's open pledge to it, if any). Exactly one of the two is set.
    ``facet`` is the first of the being's favored facets the item carried, by
    facet name, or empty when it carried none.
    """

    ceremony = models.ForeignKey(
        Ceremony,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="offerings",
    )
    being = models.ForeignKey(
        "arxii.WorshippedBeing",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="sacrifices",
        help_text="Set for a sacrifice outside a ceremony: the being it was given to.",
    )
    pledge_details = models.ForeignKey(
        "arxii.PledgeDetails",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sacrifices",
        help_text="The sacrificer's open pledge to the being when it was given, if any.",
    )
    facet = models.ForeignKey(
        "arxii.Facet",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="The first of the being's favored facets the item carried, by name.",
    )
    item_name = models.CharField(max_length=200)
    item_value = models.PositiveIntegerField(default=0)
    item_legend_value = models.PositiveIntegerField(
        default=0,
        help_text="Legend value of the offered item at sacrifice time (#2359).",
    )
    worship_grant = models.ForeignKey(
        "arxii.WorshipGrant",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    offered_by = models.ForeignKey(
        _PERSONA_MODEL, on_delete=models.PROTECT, related_name="ceremony_offerings"
    )
    outcome_tier = models.ForeignKey(
        "arxii.CheckOutcome",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text=(
            "The sacrifice roll (#4500). Empty for an item with no meaning points, an item "
            "past the week's limit, and a ceremony offering, whose rite roll is its check."
        ),
    )
    game_week = models.ForeignKey(
        "arxii.GameWeek",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The game week the item was given up in; the weekly limit counts by it.",
    )
    counted = models.BooleanField(
        default=False,
        db_default=False,
        help_text=(
            "True when the item had meaning points and a place in the week's limit, so it "
            "paid (a sacrifice rolled, an offering fed the pool). An item with no points, "
            "or past the limit, is given up for nothing and is not counted."
        ),
    )

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(ceremony__isnull=False, being__isnull=True)
                    | models.Q(ceremony__isnull=True, being__isnull=False)
                ),
                name="ceremony_offering_ceremony_xor_being",
            ),
        ]

    def __str__(self) -> str:
        if self.ceremony_id is None:
            return f"{self.item_name} sacrificed to {self.being}"
        return f"{self.item_name} offered at {self.ceremony}"


class OfferingSignal(SharedMemoryModel):
    """One meaning signal of an item at the moment it was given up (#4500, #4462).

    The item is soft-destroyed and its holder cleared, so what it meant to the one who
    gave it up is captured here. The GM's sacrifice detail, the pledge card and the
    being's dashboard read these rows; the points were computed by
    ``world.items.services.meaning.item_meaning``, which reads records and never a price.
    """

    offering = models.ForeignKey(CeremonyOffering, on_delete=models.CASCADE, related_name="signals")
    kind = models.CharField(max_length=20, choices=MeaningSignalKind.choices)
    points = models.PositiveSmallIntegerField()
    detail = models.CharField(
        max_length=200,
        blank=True,
        help_text="What made it count, such as the maker's persona name or the days held.",
    )

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} {self.points}"


class CeremonySpeech(SharedMemoryModel):
    """A recognized speech; the speaker's Oratory roll shapes honoree prestige."""

    ceremony = models.ForeignKey(Ceremony, on_delete=models.CASCADE, related_name="speeches")
    speaker = models.ForeignKey(
        _PERSONA_MODEL, on_delete=models.PROTECT, related_name="ceremony_speeches"
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
    offering_pool_per_point = models.PositiveIntegerField(
        default=5,
        help_text=(
            "Worship pool granted per meaning point of each counted item given up (#4500). "
            "Renamed from 'offering resonance per value': it was per point of the item's "
            "value, so review this number. Nothing reads an item's price."
        ),
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
    devotion_per_offering_point = models.PositiveIntegerField(
        default=5,
        help_text=(
            "Officiant favor per meaning point of each counted ceremony offering (#4500). "
            "Renamed from 'devotion per offering': review this number."
        ),
    )
    devotion_officiant = models.PositiveIntegerField(
        default=10, help_text="Devotion favor the officiant gains at finish."
    )
    offering_favored_facet_multiplier_percent = models.PositiveIntegerField(
        default=200,
        help_text=(
            "Percent multiplier on an item's meaning points when it carries a Facet the "
            "being favors (BeingFacet), #3777, #4500. 100 = no bonus."
        ),
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


class WorshipConversionOffer(SharedMemoryModel):
    """Consent gate for a CONVERSION honoree's own conversion (#2361, Ratified amendment #1a).

    One row per CeremonyHonoree on a CONVERSION-type ceremony, created when the
    ceremony opens — but ONLY when the officiant is someone other than the convert
    themself. A self-officiated solo conversion (officiant IS the honoree, the
    "temple, no officiant needed" route) never gets one: nobody needs to consent
    to their own choice. PENDING until the honoree's own controlling account
    answers (world.ceremonies.services.respond_to_conversion_offer). Accepting
    records the heart-vs-lip-service choice (Ratified amendment #2, ``is_sincere``)
    right here — finish_ceremony's CONVERSION branch reads it to decide both
    whether to repoint WorshipDeclaration.public_being at all (declined/still-
    pending honorees get nothing — the rite concludes but honors nothing, mirrors
    a declined Seance offer) and what to store for the private inward truth.
    Never mutated once ACCEPTED/DECLINED; a fresh ceremony mints a fresh row.
    """

    ceremony_honoree = models.OneToOneField(
        CeremonyHonoree, on_delete=models.CASCADE, related_name="conversion_offer"
    )
    status = models.CharField(
        max_length=20, choices=ConversionOfferStatus.choices, default=ConversionOfferStatus.PENDING
    )
    is_sincere = models.BooleanField(
        null=True,
        blank=True,
        help_text=(
            "Heart vs lip service, set on ACCEPT (Ratified amendment #2). "
            "Null while PENDING or after DECLINED."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Conversion offer for {self.ceremony_honoree} ({self.status})"


class WeddingConsentOffer(SharedMemoryModel):
    """Consent gate for a WEDDING honoree, created at ceremony START (#2358).

    Ratified 2026-08-15: the officiant's ``open_ceremony`` call creates one row
    per honoree on a WEDDING-type ceremony (mirrors ``SeanceManifestationOffer``'s
    at-open creation). Both must reach ACCEPTED before ``finish_ceremony``'s
    WEDDING branch may solemnize the betrothal — a DECLINE aborts the ceremony
    (``ABANDONED``) instead. Never mutated once ACCEPTED/DECLINED; a fresh
    ceremony mints a fresh row.
    """

    ceremony_honoree = models.OneToOneField(
        CeremonyHonoree, on_delete=models.CASCADE, related_name="wedding_consent_offer"
    )
    status = models.CharField(
        max_length=20, choices=SeanceOfferStatus.choices, default=SeanceOfferStatus.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Wedding consent for {self.ceremony_honoree} ({self.status})"


class Coronation(SharedMemoryModel):
    """The permanent record of a solemnized coronation (#2358).

    Created at ceremony FINISH, never at OPEN — an abandoned coronation
    ceremony leaves no trace, so a retry for the same (honoree, title) pair
    still works. The ``UniqueConstraint`` below is the actual one-off-per-
    title enforcement (a ducal coronation and a later imperial one for the
    same honoree are two distinct titles, so both stand); ``open_ceremony``'s
    precondition is the friendly pre-check that raises before the rite even
    begins.
    """

    ceremony = models.OneToOneField(Ceremony, on_delete=models.PROTECT, related_name="coronation")
    honoree_sheet = models.ForeignKey(
        "arxii.CharacterSheet", on_delete=models.PROTECT, related_name="coronations"
    )
    title = models.ForeignKey("arxii.Title", on_delete=models.PROTECT, related_name="coronations")
    crowned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-crowned_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["honoree_sheet", "title"], name="unique_coronation_per_honoree_title"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.honoree_sheet} crowned for {self.title}"
