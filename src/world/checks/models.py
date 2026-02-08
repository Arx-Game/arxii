"""Check system models."""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin


class CheckCategory(NaturalKeyMixin, SharedMemoryModel):
    """Grouping for check types (Social, Combat, Exploration, Magic)."""

    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    display_order = models.PositiveIntegerField(default=0)

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name_plural = "Check categories"

    def __str__(self):
        return self.name


class CheckType(NaturalKeyMixin, SharedMemoryModel):
    """Staff-defined check type with trait and aspect composition."""

    name = models.CharField(max_length=100)
    category = models.ForeignKey(
        CheckCategory,
        on_delete=models.CASCADE,
        related_name="check_types",
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name", "category"]
        dependencies = ["checks.CheckCategory"]

    class Meta:
        ordering = ["category__display_order", "display_order", "name"]
        unique_together = ["name", "category"]

    def __str__(self):
        return self.name


class CheckTypeTrait(NaturalKeyMixin, SharedMemoryModel):
    """Weighted trait contribution to a check type."""

    check_type = models.ForeignKey(
        CheckType,
        on_delete=models.CASCADE,
        related_name="traits",
    )
    trait = models.ForeignKey(
        "traits.Trait",
        on_delete=models.CASCADE,
        related_name="check_type_traits",
    )
    weight = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=1.0,
        help_text="Multiplier for this trait's contribution (default 1.0)",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["check_type", "trait"]
        dependencies = ["checks.CheckType", "traits.Trait"]

    class Meta:
        unique_together = ["check_type", "trait"]
        ordering = ["check_type", "-weight", "trait__name"]

    def __str__(self):
        return f"{self.check_type.name}: {self.trait.name} ({self.weight}x)"


class CheckTypeAspect(NaturalKeyMixin, SharedMemoryModel):
    """Weighted aspect relevance for a check type."""

    check_type = models.ForeignKey(
        CheckType,
        on_delete=models.CASCADE,
        related_name="aspects",
    )
    aspect = models.ForeignKey(
        "classes.Aspect",
        on_delete=models.CASCADE,
        related_name="check_type_aspects",
    )
    weight = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=1.0,
        help_text="Relevance multiplier for this aspect (default 1.0)",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["check_type", "aspect"]
        dependencies = ["checks.CheckType", "classes.Aspect"]

    class Meta:
        unique_together = ["check_type", "aspect"]
        ordering = ["check_type", "-weight"]

    def __str__(self):
        return f"{self.check_type.name}: {self.aspect.name} ({self.weight}x)"
