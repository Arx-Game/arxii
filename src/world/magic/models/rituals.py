"""Rituals: authored magical procedures with dual dispatch.

Ritual is the authored magical procedure, dispatched either via a service
function path, a FlowDefinition, or a scene action check. RitualComponentRequirement
enumerates item components required to perform a ritual. ImbuingProseTemplate supplies
fallback prose keyed on (resonance, target_kind).
"""

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.descriptors import ReverseOneToOneOrNone
from world.magic.constants import ParticipationRule, RitualExecutionKind, TargetKind
from world.magic.models.ritual_check_config import RitualCheckConfig


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
    - execution_kind=SCENE_ACTION: fires a check defined in RitualCheckConfig sidecar

    clean() enforces the legal shape for each mode. The sidecar invariant
    (SCENE_ACTION requires a RitualCheckConfig; other kinds may carry one)
    is enforced in clean() only since DB CHECK constraints cannot span tables.
    """

    # Reverse-OneToOne safe accessor (#2386): missing row -> None.
    check_config_or_none = ReverseOneToOneOrNone("check_config")

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
    draft_validator_path = models.CharField(max_length=255, blank=True)
    """Optional dotted path to a ``validator(*, session)`` callable run at draft
    time (mirrors service_function_path's fire dispatch). Blank = no validation."""
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
    client_hosted = models.BooleanField(
        default=False,
        help_text=(
            "When True, the generic Rituals listing page hides this ritual; "
            "it has a specialized host UI elsewhere (e.g., Thread Detail for Imbuing)."
        ),
    )

    participation_rule = models.CharField(
        max_length=32,
        choices=ParticipationRule.choices,
        default=ParticipationRule.SINGLE_ACTOR,
    )
    min_participants = models.PositiveSmallIntegerField(null=True, blank=True)
    max_participants = models.PositiveSmallIntegerField(null=True, blank=True)

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
                        # Sidecar invariant (SCENE_ACTION requires RitualCheckConfig;
                        # other kinds may carry one) is enforced in clean() only —
                        # it cannot be expressed cross-table in a DB CHECK constraint.
                        models.Q(execution_kind="SCENE_ACTION")
                        & models.Q(service_function_path="")
                        & models.Q(flow__isnull=True)
                    )
                    | (
                        # CEREMONY: no service path, no flow. Creates a
                        # PendingRitualEffect awaiting a finisher command.
                        models.Q(execution_kind="CEREMONY")
                        & models.Q(service_function_path="")
                        & models.Q(flow__isnull=True)
                    )
                ),
                name="ritual_execution_payload",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def _clean_no_service_path(self, kind: str) -> None:
        if self.service_function_path:
            raise ValidationError(
                {"service_function_path": f"{kind} rituals must not set service_function_path."}
            )

    def _clean_no_flow(self, kind: str) -> None:
        if self.flow is not None:
            raise ValidationError({"flow": f"{kind} rituals must not set flow."})

    def _clean_execution_payload(self) -> None:
        """Validate that execution payload fields match the execution_kind."""
        kind = self.execution_kind
        if kind == RitualExecutionKind.SERVICE:
            if not self.service_function_path:
                raise ValidationError({"service_function_path": "SERVICE rituals require a path."})
            self._clean_no_flow("SERVICE")
        elif kind == RitualExecutionKind.FLOW:
            if self.flow is None:
                raise ValidationError({"flow": "FLOW rituals require a FlowDefinition."})
            self._clean_no_service_path("FLOW")
        elif kind == RitualExecutionKind.SCENE_ACTION:
            self._clean_no_service_path("SCENE_ACTION")
            self._clean_no_flow("SCENE_ACTION")
        elif kind == RitualExecutionKind.CEREMONY:
            self._clean_no_service_path("CEREMONY")
            self._clean_no_flow("CEREMONY")

    def _clean_sidecar_invariant(self) -> None:
        """SCENE_ACTION rituals require a RitualCheckConfig; other kinds may carry one.

        Called only when the ritual already has a pk (config query requires a
        saved row). Cannot be a DB CHECK constraint since it spans tables.
        """
        if self.execution_kind != RitualExecutionKind.SCENE_ACTION:
            return
        if not RitualCheckConfig.objects.filter(ritual=self).exists():
            raise ValidationError(
                {"execution_kind": ("SCENE_ACTION rituals require a RitualCheckConfig.")}
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
        null=True,
        blank=True,
        related_name="ritual_requirements",
    )
    min_touchstone_tier = models.ForeignKey(
        "magic.ResonanceTier",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "Touchstone mode: any attuned item whose tied_resonance matches the "
            "performer's own claimed Resonance, at or above this tier, satisfies "
            "this requirement. Exactly one of item_template/min_touchstone_tier is set."
        ),
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

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    (
                        models.Q(item_template__isnull=False)
                        & models.Q(min_touchstone_tier__isnull=True)
                    )
                    | (
                        models.Q(item_template__isnull=True)
                        & models.Q(min_touchstone_tier__isnull=False)
                    )
                ),
                name="ritualcomponentrequirement_exactly_one_mode",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.ritual.name} needs {self.quantity}x {self.item_template_id}"


class PendingRitualEffect(SharedMemoryModel):
    """In-progress ritual ceremony awaiting a finisher command (weave / imbue).

    Created by PerformRitualAction for CEREMONY-kind rituals. Consumed and
    deleted by the finisher action (WeaveThreadAction, ImbueAction) on success.
    UniqueConstraint prevents stacking the same ceremony twice before finishing.
    """

    character = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.PROTECT,
        related_name="pending_ritual_effects",
    )
    ritual = models.ForeignKey(
        "magic.Ritual",
        on_delete=models.PROTECT,
        related_name="pending_effects",
    )
    stage = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["character", "ritual"],
                name="pending_ritual_effect_unique_per_char_ritual",
            )
        ]

    def __str__(self) -> str:
        return f"PendingRitualEffect({self.character_id}, {self.ritual.name!r})"
