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
