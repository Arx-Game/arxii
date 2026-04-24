"""Cantrips: staff-curated starter technique templates.

A Cantrip is a baby Technique. At CG finalization, the cantrip creates a real
Technique in the character's Gift. Mechanical fields (intensity, control,
anima cost) are hidden from the player; they only see name, description,
archetype grouping, and optional facet selection.
"""

from functools import cached_property

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.magic.constants import CantripArchetype
from world.magic.models.techniques import EffectType, TechniqueStyle


class Cantrip(SharedMemoryModel):
    """Staff-curated starter technique template for character creation.

    A cantrip is a baby technique — same mechanical system, just preset at low values.
    At CG finalization, the cantrip creates a real Technique in the character's Gift.
    Mechanical fields (intensity, control, anima cost) are hidden from the player;
    they only see name, description, archetype grouping, and optional facet selection.
    """

    name = models.CharField(max_length=200, unique=True)
    description = models.TextField()
    archetype = models.CharField(
        max_length=20,
        choices=CantripArchetype.choices,
        help_text="Player-facing category for CG grouping: attack, defense, buff, debuff, utility.",
    )
    effect_type = models.ForeignKey(
        EffectType,
        on_delete=models.PROTECT,
        related_name="cantrips",
        help_text="Mechanical effect type (Attack, Defense, Buff, etc.).",
    )
    style = models.ForeignKey(
        TechniqueStyle,
        on_delete=models.PROTECT,
        related_name="cantrips",
        help_text="How this cantrip manifests. Filtered by character's Path at CG.",
    )
    base_intensity = models.PositiveIntegerField(
        default=1,
        help_text="Starting intensity for the technique created from this cantrip.",
    )
    base_control = models.PositiveIntegerField(
        default=1,
        help_text="Starting control for the technique created from this cantrip.",
    )
    base_anima_cost = models.PositiveIntegerField(
        default=5,
        help_text="Starting anima cost for the technique created from this cantrip.",
    )
    requires_facet = models.BooleanField(
        default=False,
        help_text=("If true, player must pick a facet (element/damage type) from allowed_facets."),
    )
    facet_prompt = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text=(
            'Player-facing dropdown label, e.g. "Choose your element". '
            "Only used when requires_facet=True."
        ),
    )
    allowed_facets = models.ManyToManyField(
        "magic.Facet",
        blank=True,
        related_name="cantrips",
        help_text="Curated list of valid facets for this cantrip's dropdown.",
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Cantrip"
        verbose_name_plural = "Cantrips"

    @cached_property
    def cached_allowed_facets(self) -> list:
        """Allowed facets for this cantrip. Supports Prefetch(to_attr=)."""
        return list(self.allowed_facets.all())

    def __str__(self) -> str:
        return self.name
