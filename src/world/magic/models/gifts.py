"""Gifts and Traditions — character magical portfolios and schools.

Gifts are thematic collections of magical techniques.
Traditions represent schools of practice or philosophy.
"""

from django.db import models
from django.utils.functional import cached_property
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.magic.constants import GiftKind
from world.magic.models.affinity import Resonance


class GiftManager(NaturalKeyManager):
    """Manager for Gift with natural key support."""


class Gift(NaturalKeyMixin, SharedMemoryModel):
    """
    A thematic collection of magical powers.

    Gifts represent a character's supernatural portfolio - like "Shadow Majesty"
    for dark regal influence. Each Gift contains multiple Powers that unlock
    as the character levels.

    Affinities and Resonances are proper domain models.
    """

    name = models.CharField(
        max_length=200,
        unique=True,
        help_text="Display name for this gift.",
    )
    description = models.TextField(
        blank=True,
        help_text="Player-facing description of this gift.",
    )
    kind = models.CharField(
        max_length=16,
        choices=GiftKind.choices,
        default=GiftKind.MAJOR,
        db_index=True,
        help_text=(
            "Major: the one CG-chosen gift. Minor: shared/acquirable gifts that "
            "species abilities and in-play powers are delivered as (ADR-0050)."
        ),
    )
    resonances = models.ManyToManyField(
        Resonance,
        blank=True,
        related_name="gifts",
        help_text="Resonances associated with this gift.",
    )
    creator = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_gifts",
        help_text="Character who created this gift.",
    )
    codex_entry = models.ForeignKey(
        "codex.CodexEntry",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="gifts",
        help_text="Lore entry this gift is bound to, if any.",
    )

    objects = GiftManager()

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name

    def get_affinity_breakdown(self) -> dict[str, int]:
        """Derive affinity from resonances' affinities."""
        counts: dict[str, int] = {}
        for resonance in self.resonances.select_related("affinity").all():
            aff_name = resonance.affinity.name
            counts[aff_name] = counts.get(aff_name, 0) + 1
        return counts

    @cached_property
    def cached_resonances(self) -> list:
        """Resonances for this gift. Supports Prefetch(to_attr=)."""
        return list(self.resonances.all())

    @cached_property
    def cached_techniques(self) -> list:
        """Techniques for this gift. Supports Prefetch(to_attr=)."""
        return list(self.techniques.all())


class CharacterGift(SharedMemoryModel):
    """
    Links a character to a Gift they know.

    Characters start with one Gift at creation and may learn more
    through play, training, or transformation.
    """

    character = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="character_gifts",
        help_text="The character who knows this gift.",
    )
    gift = models.ForeignKey(
        Gift,
        on_delete=models.PROTECT,
        related_name="character_grants",
        help_text="The gift known.",
    )
    acquired_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this gift was acquired.",
    )

    class Meta:
        unique_together = ["character", "gift"]
        verbose_name = "Character Gift"
        verbose_name_plural = "Character Gifts"

    def __str__(self) -> str:
        return f"{self.gift} on {self.character}"


class TraditionManager(NaturalKeyManager):
    """Manager for Tradition with natural key support."""


class Tradition(NaturalKeyMixin, SharedMemoryModel):
    """
    A magical tradition representing a school of practice or philosophy.

    Traditions group practitioners who share techniques, beliefs, or methods.
    """

    @cached_property
    def cached_codex_grants(self) -> list:
        """Codex grants — the Prefetch/query shared interface (#2386).

        Authored content: negligible staleness on the identity-mapped row.
        """
        return list(self.codex_grants.all())

    name = models.CharField(
        max_length=200,
        unique=True,
        help_text="Display name for this tradition.",
    )
    description = models.TextField(
        blank=True,
        help_text="Player-facing description of this tradition's philosophy and practices.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this tradition is currently available for selection.",
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display ordering within lists (lower numbers appear first).",
    )

    objects = TraditionManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Tradition"
        verbose_name_plural = "Traditions"

    def __str__(self) -> str:
        return self.name


class CharacterTradition(SharedMemoryModel):
    """
    Links a character to a tradition they belong to.

    Characters may join traditions during creation or through play. History is
    preserved (#2441 ruling 2): switching or leaving a tradition sets ``left_at``
    on the old row rather than deleting it — the record of having been Unbound,
    or a member of a since-abandoned tradition, persists. A character has at
    most one ACTIVE (``left_at IS NULL``) row at a time, enforced by
    ``unique_active_tradition_per_character`` below — mirrors
    ``OrganizationMembership.left_at`` + its active-row constraint
    (``world.societies.models``). ``unique_together`` on (character, tradition)
    was deliberately dropped: rejoining a tradition after having left it must be
    able to create a second historical row for the same pair, which a
    character+tradition unique key would forbid. ``world.magic.services.
    tradition_membership.join_tradition``/``leave_tradition`` are the only
    writers of this row outside CG finalization (which creates the character's
    first, unconditionally-active row) and Django admin.
    """

    character = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="character_traditions",
        help_text="The character who belongs to this tradition.",
    )
    tradition = models.ForeignKey(
        Tradition,
        on_delete=models.PROTECT,
        related_name="character_traditions",
        help_text="The tradition the character belongs to.",
    )
    acquired_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the character joined this tradition.",
    )
    left_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "When the character left this tradition, voluntarily or via a switch "
            "to another tradition (#2441). Null = this is the character's "
            "currently active tradition."
        ),
    )

    class Meta:
        verbose_name = "Character Tradition"
        verbose_name_plural = "Character Traditions"
        constraints = [
            models.UniqueConstraint(
                fields=["character"],
                condition=models.Q(left_at__isnull=True),
                name="unique_active_tradition_per_character",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.tradition} on {self.character}"
