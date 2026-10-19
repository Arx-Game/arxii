"""NPC statline preset catalog (#3427).

A GM minting a Story NPC (``mint_story_npc``, ``staff_characters.py``) picks a
curated archetype -- "Guard", "Courtier" -- instead of hand-inventing stat and
skill values. Staff author the catalog; GMs only select from it (ADR-0176
stays intact -- the applied values land as the same real
``CharacterTraitValue``/``CharacterSkillValue`` rows a PC's sheet carries,
never a shortcut representation).

``NPCStatlinePreset`` is the catalog row (content-repo-owned, registered in
``CONTENT_MODELS``); ``NPCPresetTraitLine``/``NPCPresetSkillLine`` are its
child rows, applied by ``world.roster.services.staff_characters
.apply_npc_preset``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.db import models

from core.models import ArxSharedMemoryModel as SharedMemoryModel
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from evennia_extensions.cached_property import PrunedCachedProperty
from evennia_extensions.mixins import RelatedCacheClearingMixin
from world.contributors.models import CreditedContent

if TYPE_CHECKING:
    from collections.abc import Sequence


class NPCStatlinePreset(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
    """A staff-authored archetype statline a GM selects at Story NPC mint time.

    GMs never edit values directly -- they pick a preset by name; staff tune
    the catalog in admin. See ``apply_npc_preset`` for the write shape.
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Archetype name shown to GMs at mint time (e.g. 'Guard', 'Courtier').",
    )
    description = models.TextField(
        blank=True,
        help_text="Staff-facing summary of when to reach for this archetype.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["name"]
        verbose_name = "NPC Statline Preset"
        verbose_name_plural = "NPC Statline Presets"

    def __str__(self) -> str:
        return self.name

    @PrunedCachedProperty
    def cached_trait_lines(self) -> Sequence[NPCPresetTraitLine]:
        """This preset's STAT lines with their traits (the catalog list prefetches it).

        A line's save or delete clears it through ``NPCPresetTraitLine.related_cache_fields``.
        """
        return list(self.trait_lines.select_related("trait"))

    @PrunedCachedProperty
    def cached_skill_lines(self) -> Sequence[NPCPresetSkillLine]:
        """This preset's SKILL lines with their skills (the catalog list prefetches it).

        A line's save or delete clears it through ``NPCPresetSkillLine.related_cache_fields``.
        """
        return list(self.skill_lines.select_related("skill", "skill__trait"))


class NPCPresetTraitLine(RelatedCacheClearingMixin, SharedMemoryModel):
    """One STAT line on a preset, at display scale (1-10).

    ``apply_npc_preset`` converts ``display_value`` to the internal x10
    storage scale the same way CG finalize's ``_create_stat_values`` does
    (``STAT_DISPLAY_DIVISOR``, ``world.traits.models``) -- staff author in
    the scale they see on a sheet, not the internal one.
    """

    # The preset's cached line list (the catalog list reads it) follows every save.
    related_cache_fields: ClassVar[list[str]] = ["preset"]

    preset = models.ForeignKey(
        NPCStatlinePreset,
        on_delete=models.CASCADE,
        related_name="trait_lines",
    )
    # String FK ("arxii.Trait"), not a direct import: world.traits.models imports
    # world.roster.models (Trait -> RosterTenure), so a direct class import here
    # would be circular.
    trait = models.ForeignKey(
        "arxii.Trait",
        on_delete=models.PROTECT,
        related_name="npc_preset_trait_lines",
        help_text="A STAT trait. PROTECT: deleting a referenced trait requires clearing "
        "the preset line first, rather than silently truncating the archetype.",
    )
    display_value = models.PositiveSmallIntegerField(
        help_text="Display-scale value (1-10), mirroring CG's stat-allocation scale."
    )

    class Meta:
        ordering = ["preset", "trait"]
        constraints = [
            models.UniqueConstraint(
                fields=["preset", "trait"],
                name="roster_npc_preset_trait_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.preset_id}: {self.trait_id}={self.display_value}"


class NPCPresetSkillLine(RelatedCacheClearingMixin, SharedMemoryModel):
    """One SKILL line on a preset, at true 1-100 scale.

    Skills store and display the same value (no x10 conversion, unlike
    stats) -- see ``STAT_DISPLAY_DIVISOR``'s docstring in
    ``world.traits.models``.
    """

    # The preset's cached line list (the catalog list reads it) follows every save.
    related_cache_fields: ClassVar[list[str]] = ["preset"]

    preset = models.ForeignKey(
        NPCStatlinePreset,
        on_delete=models.CASCADE,
        related_name="skill_lines",
    )
    # String FK for the same reason as NPCPresetTraitLine.trait above --
    # world.skills.models.Skill wraps a Trait, so it inherits the same cycle.
    skill = models.ForeignKey(
        "arxii.Skill",
        on_delete=models.PROTECT,
        related_name="npc_preset_skill_lines",
        help_text="PROTECT: mirrors NPCPresetTraitLine.trait's rationale.",
    )
    value = models.PositiveSmallIntegerField(
        help_text="True 1-100 skill value -- no display-scale conversion, matching "
        "CharacterSkillValue."
    )

    class Meta:
        ordering = ["preset", "skill"]
        constraints = [
            models.UniqueConstraint(
                fields=["preset", "skill"],
                name="roster_npc_preset_skill_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.preset_id}: {self.skill_id}={self.value}"
