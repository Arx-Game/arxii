"""Models for the gem value model (Build 0b slice 1).

All models set ``Meta.app_label = "items"`` (registered under the ``items`` app,
mirroring ``world.items.crafting``).
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.items.gems.constants import (
    GEM_QUALITY_LEVEL_MAX,
    GEM_QUALITY_LEVEL_MIN,
    GemAxis,
)

_ITEM_TEMPLATE_FK = "items.ItemTemplate"
_ITEM_INSTANCE_FK = "items.ItemInstance"
_GEM_GRADE_FK = "items.GemGrade"


class GemGrade(SharedMemoryModel):
    """One grade on one gem axis (size / purity / cut) — a word + a worth multiplier.

    Grades are authored data (admin-editable). The lowest grade of each axis
    multiplies by 1.0 (the floor); higher grades scale worth up. Presentation shows
    the ``label`` word; the ``multiplier`` stays backstage.
    """

    axis = models.CharField(
        max_length=10,
        choices=GemAxis.choices,
        help_text="Which gem axis this grade belongs to.",
    )
    sort_order = models.PositiveSmallIntegerField(
        help_text="Ordering within the axis (lower = worse; the lowest is the 1.0 floor).",
    )
    label = models.CharField(
        max_length=40,
        help_text="Player-facing word for this grade (e.g. 'large', 'cloudy', 'uncut').",
    )
    multiplier = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(1)],
        help_text="Worth multiplier for this grade (>= 1.0; the axis floor is 1.0).",
    )

    class Meta:
        app_label = "items"
        ordering = ["axis", "sort_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["axis", "sort_order"],
                name="items_gemgrade_axis_sortorder_unique",
            ),
            models.UniqueConstraint(
                fields=["axis", "label"],
                name="items_gemgrade_axis_label_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_axis_display()}: {self.label} (×{self.multiplier})"


class GemDetails(SharedMemoryModel):
    """Sidecar marking an ``ItemTemplate`` as a gem *type* (ruby, opal, duskstone).

    OneToOne to ``ItemTemplate`` (``SanctumDetails``/``LabStationDetails`` shape) so a
    gem type is an ordinary template — requirable/consumable by
    ``CraftingMaterialRequirement`` / ``RitualComponentRequirement`` and holdable as an
    ``ItemInstance``. The template's tier is its ``material_category`` (0a); its motif
    reuses ``ItemTemplate.tied_resonance``. ``quality_level`` is the 1-15 Arx-1 scale.
    """

    item_template = models.OneToOneField(
        _ITEM_TEMPLATE_FK,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="gem_details",
    )
    quality_level = models.PositiveSmallIntegerField(
        validators=[
            MinValueValidator(GEM_QUALITY_LEVEL_MIN),
            MaxValueValidator(GEM_QUALITY_LEVEL_MAX),
        ],
        help_text="Gem type quality level 1-15 (1-5 semiprecious, 6-10 precious, 11-15 magical).",
    )

    class Meta:
        app_label = "items"

    def __str__(self) -> str:
        return f"gem type {self.item_template_id} (level {self.quality_level})"


class GemInstanceDetails(SharedMemoryModel):
    """Sidecar marking an ``ItemInstance`` as a cut/graded gem.

    Carries the three per-instance grades. Worth = ``template.value × size × purity ×
    cut`` (see ``world.items.gems.services.compute_gem_worth``), which ``appraise()``
    uses in place of the quality-tier multiplier for gems.
    """

    item_instance = models.OneToOneField(
        _ITEM_INSTANCE_FK,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="gem_instance_details",
    )
    size_grade = models.ForeignKey(_GEM_GRADE_FK, on_delete=models.PROTECT, related_name="+")
    purity_grade = models.ForeignKey(_GEM_GRADE_FK, on_delete=models.PROTECT, related_name="+")
    cut_grade = models.ForeignKey(_GEM_GRADE_FK, on_delete=models.PROTECT, related_name="+")

    class Meta:
        app_label = "items"

    def __str__(self) -> str:
        return (
            f"gem {self.item_instance_id}: "
            f"{self.size_grade.label}/{self.purity_grade.label}/{self.cut_grade.label}"
        )

    def clean(self) -> None:
        """Each grade FK must point at a GemGrade on its own axis."""
        super().clean()
        mismatches = [
            field
            for field, expected in (
                ("size_grade", GemAxis.SIZE),
                ("purity_grade", GemAxis.PURITY),
                ("cut_grade", GemAxis.CUT),
            )
            if (grade := getattr(self, field, None)) is not None and grade.axis != expected
        ]
        if mismatches:
            raise ValidationError(
                {
                    field: f"Must reference a {field.split('_')[0]}-axis GemGrade."
                    for field in mismatches
                }
            )
