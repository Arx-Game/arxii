"""Worship foundation models (#2355).

Gods, spirits, totems, and dark powers as authorable entities (``WorshippedBeing``)
that accumulate worship in a vast resonance pool, fed by ceremonies (#2289) and
future worship acts. Beings are deliberately NOT CharacterSheets (see the ADR in
this PR): most gods are never played; the rare manifested god links an
``avatar_sheet``. Consumers (ceremonies, miracles) point INTO this app; it imports
no consumer system (ADR-0010).
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


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
