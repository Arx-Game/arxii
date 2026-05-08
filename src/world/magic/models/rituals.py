"""Rituals: authored magical procedures with dual dispatch.

Ritual is the authored magical procedure, dispatched either via a service
function path, a FlowDefinition, or a scene action check. RitualComponentRequirement
enumerates item components required to perform a ritual. ImbuingProseTemplate supplies
fallback prose keyed on (resonance, target_kind).
"""

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.magic.constants import RitualExecutionKind, TargetKind
from world.magic.models.ritual_scene_action import RitualSceneActionConfig


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
    """A ritual: authored magical procedure executed via service, flow, or scene action.

    Spec A §4.3. Each Ritual is dispatched via one of three modes:
    - execution_kind=SERVICE: invokes a registered service function path
    - execution_kind=FLOW: invokes a FlowDefinition
    - execution_kind=SCENE_ACTION: fires a check defined in RitualSceneActionConfig sidecar

    clean() enforces the legal shape for each mode. The sidecar invariant
    (SCENE_ACTION requires a RitualSceneActionConfig; others must not have one)
    is enforced in clean() only since DB CHECK constraints cannot span tables.
    """

    name = models.CharField(max_length=120, unique=True)
    description = models.TextField()
    hedge_accessible = models.BooleanField(default=False)
    glimpse_eligible = models.BooleanField(default=False)
    narrative_prose = models.TextField()
    input_schema = models.JSONField(
        null=True,
        blank=True,
        help_text=(
            "UI-rendering metadata: what kwargs the perform endpoint expects. "
            "Shape: {'fields': [{'name': str, 'label': str, 'type': str, 'required': bool, ...}]}. "
            "When None, the ritual takes no player-supplied kwargs."
        ),
    )

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
    author_account = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="authored_rituals",
        help_text="The player account that authored this ritual. NULL = staff-authored.",
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
                    | (
                        # SCENE_ACTION: no service path, no flow.
                        # Sidecar invariant (requires RitualSceneActionConfig) is
                        # enforced in clean() only — it cannot be expressed cross-table
                        # in a DB CHECK constraint.
                        models.Q(execution_kind="SCENE_ACTION")
                        & models.Q(service_function_path="")
                        & models.Q(flow__isnull=True)
                    )
                ),
                name="ritual_execution_payload",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def _clean_execution_payload(self) -> None:
        """Validate that execution payload fields match the execution_kind."""
        kind = self.execution_kind
        if kind == RitualExecutionKind.SERVICE:
            if not self.service_function_path:
                raise ValidationError({"service_function_path": "SERVICE rituals require a path."})
            if self.flow is not None:
                raise ValidationError({"flow": "SERVICE rituals must not set flow."})
        elif kind == RitualExecutionKind.FLOW:
            if self.flow is None:
                raise ValidationError({"flow": "FLOW rituals require a FlowDefinition."})
            if self.service_function_path:
                raise ValidationError(
                    {"service_function_path": "FLOW rituals must not set service_function_path."}
                )
        elif kind == RitualExecutionKind.SCENE_ACTION:
            if self.service_function_path:
                raise ValidationError(
                    {
                        "service_function_path": (
                            "SCENE_ACTION rituals must not set service_function_path."
                        )
                    }
                )
            if self.flow is not None:
                raise ValidationError({"flow": "SCENE_ACTION rituals must not set flow."})

    def _clean_sidecar_invariant(self) -> None:
        """Enforce the SCENE_ACTION ↔ RitualSceneActionConfig sidecar invariant.

        Called only when the ritual already has a pk (sidecar query requires a saved row).
        Cannot be expressed as a DB CHECK constraint since it spans tables.
        """
        has_sidecar = RitualSceneActionConfig.objects.filter(ritual=self).exists()
        is_scene_action = self.execution_kind == RitualExecutionKind.SCENE_ACTION
        if is_scene_action and not has_sidecar:
            raise ValidationError(
                {
                    "execution_kind": (
                        "SCENE_ACTION rituals require a RitualSceneActionConfig sidecar."
                    )
                }
            )
        if not is_scene_action and has_sidecar:
            raise ValidationError(
                {
                    "execution_kind": (
                        f"{self.execution_kind} rituals must not have a "
                        "RitualSceneActionConfig sidecar."
                    )
                }
            )

    def clean(self) -> None:
        super().clean()
        self._clean_execution_payload()
        if self.pk is not None:
            self._clean_sidecar_invariant()


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
