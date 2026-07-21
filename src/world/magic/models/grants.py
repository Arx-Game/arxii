"""Ritual grant tables for character creation.

Five sources that grant CharacterRitualKnowledge rows during CG reconciliation
(Task 1.3). Each is a simple two-FK model mirroring the codex grant pattern
in world.codex.models (BeginningsCodexGrant, PathCodexGrant, etc.).

Also carries ``DistinctionResonanceGrant`` — the currency-knob sidecar for
#1834 (distinctions granting resonance): flat seed amount + earn-rate bonus,
both rank-scaled by the character's rank in the distinction. Its reverse
sidecar, ``DistinctionResonanceRankThreshold`` (#2037), authors the opposite
direction: sustained investment in a Resonance ranking up a held Distinction.
"""

from decimal import Decimal

from django.core.validators import MaxValueValidator
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin

# App-qualified model paths repeated across FK references; centralized for dedup.
_DISTINCTION_MODEL = "distinctions.Distinction"
_PATH_MODEL = "classes.Path"
_GIFT_MODEL = "magic.Gift"
_TRADITION_MODEL = "magic.Tradition"


class BeginningsRitualGrant(SharedMemoryModel):
    """Rituals granted by a Beginnings choice."""

    beginnings = models.ForeignKey(
        "character_creation.Beginnings",
        on_delete=models.CASCADE,
        related_name="ritual_grants",
    )
    ritual = models.ForeignKey(
        "magic.Ritual",
        on_delete=models.CASCADE,
        related_name="+",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["beginnings", "ritual"],
                name="unique_beginnings_ritual_grant",
            ),
        ]
        verbose_name = "Beginnings Ritual Grant"
        verbose_name_plural = "Beginnings Ritual Grants"

    def __str__(self) -> str:
        return f"{self.beginnings} grants {self.ritual}"


# Idmapper metaclass sets attrs["path"] which shadows the "path" FK.
# Same pattern as PathCodexGrant in world.codex.models.
class PathRitualGrant(models.Model):  # noqa: SHARED_MEMORY
    """Rituals granted by a Path choice."""

    path = models.ForeignKey(
        _PATH_MODEL,
        on_delete=models.CASCADE,
        related_name="ritual_grants",
    )
    ritual = models.ForeignKey(
        "magic.Ritual",
        on_delete=models.CASCADE,
        related_name="+",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["path", "ritual"],
                name="unique_path_ritual_grant",
            ),
        ]
        verbose_name = "Path Ritual Grant"
        verbose_name_plural = "Path Ritual Grants"

    def __str__(self) -> str:
        return f"{self.path} grants {self.ritual}"


# Idmapper metaclass sets attrs["path"] which shadows the "path" FK.
# Same pattern as PathRitualGrant above / PathCodexGrant in world.codex.models.
class PathGiftGrant(NaturalKeyMixin, models.Model):  # noqa: SHARED_MEMORY
    """Gift + curated starter technique set available to a Path.

    The (Path x Gift) -> technique-set leg of ADR-0055 (#1579): the same authored
    Gift yields a different starter set per Path (a warrior-line and a spy-line path
    can both grant Pyromancy, but grant different techniques from it). As of #2426
    this row is a (path x gift) *availability pool*, not solely a crossing payload:
    character creation lets the player pick from it at level 1, and
    ``world.magic.services.path_magic.grant_path_magic`` still mints CharacterGift +
    CharacterTechnique rows from it on later path crossings.
    """

    path = models.ForeignKey(
        _PATH_MODEL,
        on_delete=models.CASCADE,
        related_name="gift_grants",
    )
    gift = models.ForeignKey(
        _GIFT_MODEL,
        on_delete=models.PROTECT,
        related_name="path_grants",
    )
    starter_techniques = models.ManyToManyField(
        "magic.Technique",
        blank=True,
        related_name="granted_by_path_gifts",
        help_text=("Curated subset of this gift's techniques minted on crossing into this path."),
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["path", "gift"]
        dependencies = [_PATH_MODEL, _GIFT_MODEL]

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["path", "gift"],
                name="unique_path_gift_grant",
            ),
        ]
        verbose_name = "Path Gift Grant"
        verbose_name_plural = "Path Gift Grants"

    def __str__(self) -> str:
        return f"{self.path} grants {self.gift}"

    def clean(self) -> None:
        super().clean()
        # M2M rows are only queryable once the grant row exists (admin / test
        # save-then-validate). Every starter technique must belong to this gift.
        if self.pk:
            mismatched = [t for t in self.starter_techniques.all() if t.gift_id != self.gift_id]
            if mismatched:
                from django.core.exceptions import ValidationError  # noqa: PLC0415

                raise ValidationError(
                    {"starter_techniques": ("Every starter technique must belong to this gift.")}
                )


class TraditionGiftGrant(NaturalKeyMixin, SharedMemoryModel):
    """Gift + curated signature technique set available to a Tradition (#2426).

    The (Tradition x Gift) sibling of ``PathGiftGrant`` above — the CG-availability
    pool a player picks from when choosing techniques for a Gift tied to their
    Tradition. Distinct from ``OrganizationGiftGrant`` (``world.societies`` — a
    project-acquired org capability granted through play, not an authored CG
    availability pool).
    """

    tradition = models.ForeignKey(
        _TRADITION_MODEL,
        on_delete=models.CASCADE,
        related_name="gift_grants",
    )
    gift = models.ForeignKey(
        _GIFT_MODEL,
        on_delete=models.PROTECT,
        related_name="tradition_grants",
    )
    signature_techniques = models.ManyToManyField(
        "magic.Technique",
        blank=True,
        related_name="granted_by_tradition_gifts",
        help_text=(
            "Curated subset of this gift's techniques available to characters "
            "picking this gift under this tradition."
        ),
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["tradition", "gift"]
        dependencies = [_TRADITION_MODEL, _GIFT_MODEL]

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tradition", "gift"],
                name="unique_tradition_gift_grant",
            ),
        ]
        verbose_name = "Tradition Gift Grant"
        verbose_name_plural = "Tradition Gift Grants"

    def __str__(self) -> str:
        return f"{self.tradition} grants {self.gift}"

    def clean(self) -> None:
        super().clean()
        # M2M rows are only queryable once the grant row exists (admin / test
        # save-then-validate). Every signature technique must belong to this gift.
        if self.pk:
            mismatched = [t for t in self.signature_techniques.all() if t.gift_id != self.gift_id]
            if mismatched:
                from django.core.exceptions import ValidationError  # noqa: PLC0415

                raise ValidationError(
                    {
                        "signature_techniques": (
                            "Every signature technique must belong to this gift."
                        )
                    }
                )


class DistinctionRitualGrant(SharedMemoryModel):
    """Rituals granted by a Distinction."""

    distinction = models.ForeignKey(
        _DISTINCTION_MODEL,
        on_delete=models.CASCADE,
        related_name="ritual_grants",
    )
    ritual = models.ForeignKey(
        "magic.Ritual",
        on_delete=models.CASCADE,
        related_name="+",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["distinction", "ritual"],
                name="unique_distinction_ritual_grant",
            ),
        ]
        verbose_name = "Distinction Ritual Grant"
        verbose_name_plural = "Distinction Ritual Grants"

    def __str__(self) -> str:
        return f"{self.distinction} grants {self.ritual}"


class DistinctionResonanceGrant(SharedMemoryModel):
    """Currency knobs a Distinction grants in a Resonance (#1834).

    A join between a Distinction and a Resonance carrying the authoring
    surface for two rank-scaled currency knobs: a flat seed amount and an
    earn-rate bonus. Both are scaled by the character's rank in the
    distinction; the scaling itself is applied by consumers of this row, not
    here. Sidecar lives in ``world.magic`` (per ADR-0010: the general
    primitive is ``magic.Resonance``, so ``distinctions`` gains no import
    into ``magic``).
    """

    distinction = models.ForeignKey(
        _DISTINCTION_MODEL,
        on_delete=models.CASCADE,
        related_name="resonance_grants",
    )
    resonance = models.ForeignKey(
        "magic.Resonance",
        on_delete=models.PROTECT,
        related_name="distinction_grants",
    )
    flat_amount_per_rank = models.PositiveIntegerField(
        default=0,
        help_text="Flat resonance seeded per rank held in the distinction.",
    )
    earn_rate_bonus_per_rank = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal(0),
        validators=[MaxValueValidator(Decimal("5.00"))],
        help_text="Earn-rate bonus per rank held in the distinction.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["distinction", "resonance"],
                name="unique_distinction_resonance_grant",
            ),
        ]
        ordering = ["distinction_id", "resonance_id"]
        verbose_name = "Distinction Resonance Grant"
        verbose_name_plural = "Distinction Resonance Grants"

    def __str__(self) -> str:
        return f"{self.distinction} grants {self.resonance}"


class DistinctionResonanceRankThreshold(SharedMemoryModel):
    """Reverse sidecar of ``DistinctionResonanceGrant`` (#2037 Decision 8).

    ``DistinctionResonanceGrant`` models Distinction -> Resonance (a distinction seeds/
    accelerates a resonance). This is the reverse direction: "sustained investment in
    THIS Resonance ranks up THAT Distinction" — the identity-reinforcing-play leg Tehom
    named ("sustained endorsements around one resonance ranking up an associated
    Distinction"). Lives in ``world.magic`` (not ``world.distinctions``) for the same
    ADR-0010 reason as its sibling: the general primitive (``magic.Resonance``) must not
    import back into a dependent app.

    Consumed by ``check_distinction_rank_thresholds``
    (``world.magic.services.distinction_resonance``): a character who already holds
    ``distinction`` and whose ``CharacterResonance.lifetime_earned`` for ``resonance``
    reaches ``lifetime_earned_threshold`` is ranked up to ``rank`` via
    ``world.distinctions.services.grant_distinction`` — never grants the distinction
    fresh, only ranks up an existing holder.
    """

    distinction = models.ForeignKey(
        _DISTINCTION_MODEL,
        on_delete=models.CASCADE,
        related_name="resonance_rank_thresholds",
    )
    resonance = models.ForeignKey(
        "magic.Resonance",
        on_delete=models.PROTECT,
        related_name="distinction_rank_thresholds",
    )
    rank = models.PositiveIntegerField(
        help_text="Which rank of the distinction this threshold unlocks.",
    )
    lifetime_earned_threshold = models.PositiveIntegerField(
        help_text=(
            "CharacterResonance.lifetime_earned in this resonance required to reach the above rank."
        ),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["distinction", "resonance", "rank"],
                name="unique_distinction_resonance_rank_threshold",
            ),
        ]
        ordering = ["distinction_id", "resonance_id", "rank"]
        verbose_name = "Distinction Resonance Rank Threshold"
        verbose_name_plural = "Distinction Resonance Rank Thresholds"

    def __str__(self) -> str:
        return f"{self.distinction} rank {self.rank} via {self.resonance}"


class TraditionRitualGrant(SharedMemoryModel):
    """Rituals granted by a Tradition."""

    tradition = models.ForeignKey(
        _TRADITION_MODEL,
        on_delete=models.CASCADE,
        related_name="ritual_grants",
    )
    ritual = models.ForeignKey(
        "magic.Ritual",
        on_delete=models.CASCADE,
        related_name="+",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tradition", "ritual"],
                name="unique_tradition_ritual_grant",
            ),
        ]
        verbose_name = "Tradition Ritual Grant"
        verbose_name_plural = "Tradition Ritual Grants"

    def __str__(self) -> str:
        return f"{self.tradition} grants {self.ritual}"


class CodexEntryRitualGrant(SharedMemoryModel):
    """Rituals granted by learning a Codex entry.

    Addition beyond the four codex grant tables — codex entries can unlock
    ritual knowledge in addition to lore knowledge.
    """

    codex_entry = models.ForeignKey(
        "codex.CodexEntry",
        on_delete=models.CASCADE,
        related_name="ritual_grants",
    )
    ritual = models.ForeignKey(
        "magic.Ritual",
        on_delete=models.CASCADE,
        related_name="+",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["codex_entry", "ritual"],
                name="unique_codex_entry_ritual_grant",
            ),
        ]
        verbose_name = "Codex Entry Ritual Grant"
        verbose_name_plural = "Codex Entry Ritual Grants"

    def __str__(self) -> str:
        return f"{self.codex_entry} grants {self.ritual}"
