from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.species.models import Species, SpeciesOrigin


class TraitType(models.TextChoices):
    COLOR = "color", "Color"
    STYLE = "style", "Style"


class FormTrait(SharedMemoryModel):
    """Definition of a physical characteristic type (e.g., hair_color, ear_type)."""

    name = models.CharField(max_length=50, unique=True, help_text="Internal key")
    display_name = models.CharField(max_length=100, help_text="Display name for UI")
    trait_type = models.CharField(max_length=20, choices=TraitType.choices, default=TraitType.STYLE)
    sort_order = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return self.display_name


class FormTraitOption(SharedMemoryModel):
    """A valid value for a trait (e.g., 'black' for hair_color)."""

    trait = models.ForeignKey(FormTrait, on_delete=models.CASCADE, related_name="options")
    name = models.CharField(max_length=50, help_text="Internal key")
    display_name = models.CharField(max_length=100, help_text="Display name for UI")
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = [["trait", "name"]]

    def __str__(self):
        return f"{self.trait.display_name}: {self.display_name}"


class SpeciesFormTrait(SharedMemoryModel):
    """Links a species to which traits it has available in CG."""

    species = models.ForeignKey(Species, on_delete=models.CASCADE, related_name="form_traits")
    trait = models.ForeignKey(FormTrait, on_delete=models.CASCADE, related_name="species_links")
    is_available_in_cg = models.BooleanField(
        default=True, help_text="Show this trait in character creation"
    )

    class Meta:
        unique_together = [["species", "trait"]]
        verbose_name = "Species Form Trait"
        verbose_name_plural = "Species Form Traits"

    def __str__(self):
        return f"{self.species.name} - {self.trait.display_name}"


class SpeciesOriginTraitOption(SharedMemoryModel):
    """Override available options for a trait at the origin level."""

    species_origin = models.ForeignKey(
        SpeciesOrigin, on_delete=models.CASCADE, related_name="trait_option_overrides"
    )
    trait = models.ForeignKey(FormTrait, on_delete=models.CASCADE, related_name="origin_overrides")
    option = models.ForeignKey(
        FormTraitOption, on_delete=models.CASCADE, related_name="origin_overrides"
    )
    is_available = models.BooleanField(
        default=True, help_text="True=add this option, False=remove it"
    )

    class Meta:
        unique_together = [["species_origin", "trait", "option"]]
        verbose_name = "Species Origin Trait Option"
        verbose_name_plural = "Species Origin Trait Options"

    def __str__(self):
        action = "+" if self.is_available else "-"
        return f"{self.species_origin}: {action}{self.option.display_name}"
