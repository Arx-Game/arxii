"""Attempt system models — narrative consequences wrapping the check system."""

from django.core.validators import MinValueValidator
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin


class AttemptCategory(NaturalKeyMixin, SharedMemoryModel):
    """Grouping for attempt templates (Infiltration, Social, Combat, Survival)."""

    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    display_order = models.PositiveIntegerField(default=0)

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name_plural = "Attempt categories"

    def __str__(self):
        return self.name


class AttemptTemplate(NaturalKeyMixin, SharedMemoryModel):
    """Reusable staff-defined attempt wrapping a check type with narrative consequences."""

    name = models.CharField(max_length=100)
    category = models.ForeignKey(
        AttemptCategory,
        on_delete=models.CASCADE,
        related_name="templates",
    )
    check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.PROTECT,
        related_name="attempt_templates",
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name", "category"]
        dependencies = ["attempts.AttemptCategory", "checks.CheckType"]

    class Meta:
        ordering = ["category__display_order", "display_order", "name"]
        unique_together = ["name", "category"]

    def __str__(self):
        return self.name


class AttemptConsequence(NaturalKeyMixin, SharedMemoryModel):
    """A single possible consequence within an attempt template, tied to an outcome tier."""

    attempt_template = models.ForeignKey(
        AttemptTemplate,
        on_delete=models.CASCADE,
        related_name="consequences",
    )
    outcome_tier = models.ForeignKey(
        "traits.CheckOutcome",
        on_delete=models.CASCADE,
        related_name="attempt_consequences",
    )
    label = models.CharField(
        max_length=200,
        help_text='Narrative text shown on roulette (e.g. "Guard raises alarm")',
    )
    mechanical_description = models.TextField(
        blank=True,
        help_text='Optional mechanical trigger description (e.g. "apply Wanted condition")',
    )
    weight = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Probability weight within this outcome tier (minimum 1)",
    )
    character_loss = models.BooleanField(
        default=False,
        help_text="If True, marks this consequence as permanent character removal",
    )
    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Ordering on the roulette within tier",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["attempt_template", "label"]
        dependencies = ["attempts.AttemptTemplate", "traits.CheckOutcome"]

    class Meta:
        unique_together = ["attempt_template", "label"]

    def __str__(self):
        return f"{self.attempt_template.name}: {self.label}"
