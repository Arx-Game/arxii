"""Rituals: authored magical procedures with dual dispatch.

Ritual is the authored magical procedure, dispatched either via a service
function path or a FlowDefinition. RitualComponentRequirement enumerates
item components required to perform a ritual. ImbuingProseTemplate supplies
fallback prose keyed on (resonance, target_kind).
"""

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.magic.constants import RitualExecutionKind, TargetKind


class ImbuingProseTemplate(SharedMemoryModel):
    """Authored fallback prose for imbuing flow templates.

    Lookup keyed (resonance, target_kind). Either field nullable; the row
    where both are NULL is the universal fallback used when no more-specific
    template matches. Spec A §4.3.
    """

    resonance = models.ForeignKey(
        "magic.Resonance",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="imbuing_prose",
    )
    target_kind = models.CharField(
        max_length=32,
        choices=TargetKind.choices,
        null=True,
        blank=True,
    )
    prose = models.TextField()

    class Meta:
        unique_together = (("resonance", "target_kind"),)

    def __str__(self) -> str:
        res = self.resonance.name if self.resonance else "*"
        tk = self.target_kind or "*"
        return f"ImbuingProse({res} / {tk})"


class Ritual(SharedMemoryModel):
    """A ritual: authored magical procedure executed via service or flow.

    Spec A §4.3. Each Ritual is dispatched either via a registered service
    function (execution_kind=SERVICE) or via a flow definition
    (execution_kind=FLOW); never both. clean() enforces the legal shape.
    """

    name = models.CharField(max_length=120, unique=True)
    description = models.TextField()
    hedge_accessible = models.BooleanField(default=False)
    glimpse_eligible = models.BooleanField(default=False)
    narrative_prose = models.TextField()

    execution_kind = models.CharField(
        max_length=16,
        choices=RitualExecutionKind.choices,
    )
    service_function_path = models.CharField(max_length=255, blank=True)
    flow = models.ForeignKey(
        "flows.FlowDefinition",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="rituals",
    )

    site_property = models.ForeignKey(
        "mechanics.Property",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ritual_sites",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    (
                        models.Q(execution_kind="SERVICE")
                        & ~models.Q(service_function_path="")
                        & models.Q(flow__isnull=True)
                    )
                    | (
                        models.Q(execution_kind="FLOW")
                        & models.Q(service_function_path="")
                        & models.Q(flow__isnull=False)
                    )
                ),
                name="ritual_execution_payload",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        if self.execution_kind == RitualExecutionKind.SERVICE:
            if not self.service_function_path:
                raise ValidationError({"service_function_path": "SERVICE rituals require a path."})
            if self.flow is not None:
                raise ValidationError({"flow": "SERVICE rituals must not set flow."})
        elif self.execution_kind == RitualExecutionKind.FLOW:
            if self.flow is None:
                raise ValidationError({"flow": "FLOW rituals require a FlowDefinition."})
            if self.service_function_path:
                raise ValidationError(
                    {"service_function_path": ("FLOW rituals must not set service_function_path.")}
                )


class RitualComponentRequirement(SharedMemoryModel):
    """A component an actor must consume / supply to perform a Ritual.

    Spec A §4.3. Quantity is the count of items required; min_quality_tier
    optionally constrains the minimum acceptable QualityTier.
    """

    ritual = models.ForeignKey(
        "magic.Ritual",
        on_delete=models.CASCADE,
        related_name="requirements",
    )
    item_template = models.ForeignKey(
        "items.ItemTemplate",
        on_delete=models.PROTECT,
        related_name="ritual_requirements",
    )
    quantity = models.PositiveSmallIntegerField(default=1)
    min_quality_tier = models.ForeignKey(
        "items.QualityTier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    authored_provenance = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"{self.ritual.name} needs {self.quantity}x {self.item_template_id}"
