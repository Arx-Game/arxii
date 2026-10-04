"""Manifesting a bound entity (#4118): the authored options on a technique and the
per-character choice among them."""

from __future__ import annotations

from django.db import models

from core.models import ArxSharedMemoryModel as SharedMemoryModel
from world.combat.constants import OpponentTier


class TechniqueManifestOption(SharedMemoryModel):
    """One entity a technique can bring into a fight (#4118).

    A technique with at least one option row is a manifesting technique. Exactly one of
    ``being`` and ``archetype`` is set. ``tier`` sizes a being's arrival (its stats come
    from the tier-scaling block); an archetype option takes its stats from the archetype.
    A low-tier option on an ordinary technique is a limited form; a high-tier option on
    an ultimate is the full arrival.
    """

    technique = models.ForeignKey(
        "arxii.Technique", on_delete=models.CASCADE, related_name="manifest_options"
    )
    being = models.ForeignKey(
        "arxii.WorshippedBeing",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="manifest_options",
    )
    archetype = models.ForeignKey(
        "arxii.CompanionArchetype",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="manifest_options",
    )
    tier = models.CharField(
        max_length=20,
        choices=OpponentTier.choices,
        default=OpponentTier.MOOK,
        help_text="Opponent tier of a being's arrival. Ignored for an archetype option.",
    )

    class Meta:
        verbose_name = "Technique Manifest Option"
        verbose_name_plural = "Technique Manifest Options"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(being__isnull=False, archetype__isnull=True)
                    | models.Q(being__isnull=True, archetype__isnull=False)
                ),
                name="manifest_option_exactly_one_entity",
            ),
            models.UniqueConstraint(
                fields=["technique", "being"],
                condition=models.Q(being__isnull=False),
                name="unique_manifest_option_being",
            ),
            models.UniqueConstraint(
                fields=["technique", "archetype"],
                condition=models.Q(archetype__isnull=False),
                name="unique_manifest_option_archetype",
            ),
        ]

    def __str__(self) -> str:
        entity = self.being or self.archetype
        return f"{self.technique} manifests {entity}"


class CharacterManifestation(SharedMemoryModel):
    """A character's version of a manifesting technique: which option they bring (#4118).

    Keyed by (character, technique), not hung on CharacterTechnique, because an ultimate
    has no CharacterTechnique row (it is a KnownUltimate). GMs and staff set it; its
    clean() (Task 3) enforces that the option belongs to the technique and the character
    is bonded to the entity.
    """

    character = models.ForeignKey(
        "arxii.CharacterSheet", on_delete=models.CASCADE, related_name="manifestations"
    )
    technique = models.ForeignKey(
        "arxii.Technique", on_delete=models.PROTECT, related_name="character_manifestations"
    )
    option = models.ForeignKey(
        TechniqueManifestOption, on_delete=models.PROTECT, related_name="character_choices"
    )
    companion = models.ForeignKey(
        "arxii.Companion",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="manifestations",
        help_text="For an archetype option: the character's own companion of that archetype.",
    )

    class Meta:
        verbose_name = "Character Manifestation"
        verbose_name_plural = "Character Manifestations"
        constraints = [
            models.UniqueConstraint(
                fields=["character", "technique"], name="unique_character_manifestation"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.character} manifests {self.option}"
