"""
API views for conditions system.

Provides read-only endpoints for:
- Lookup data (categories, damage types, capabilities, check types)
- Condition templates (browsing available conditions)
- Active conditions on characters (for character sheet)
- Condition summaries with aggregated effects
"""

from django.db.models import Q
from evennia.objects.models import ObjectDB
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from web.api.mixins import CharacterContextMixin
from world.conditions.constants import CapabilityEffectType
from world.conditions.models import (
    CapabilityType,
    CheckType,
    ConditionCapabilityEffect,
    ConditionCategory,
    ConditionCheckModifier,
    ConditionInstance,
    ConditionResistanceModifier,
    ConditionTemplate,
    DamageType,
)
from world.conditions.serializers import (
    CapabilityTypeSerializer,
    CheckTypeSerializer,
    ConditionCategorySerializer,
    ConditionInstanceObserverSerializer,
    ConditionInstanceSerializer,
    ConditionTemplateDetailSerializer,
    ConditionTemplateSerializer,
    DamageTypeSerializer,
)
from world.conditions.services import (
    get_active_conditions,
    get_aggro_priority,
    get_turn_order_modifier,
)
from world.conditions.types import CapabilitySummary, EffectLookups

# =============================================================================
# Lookup Table ViewSets
# =============================================================================


class ConditionCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for condition categories.

    Read-only endpoint for retrieving category definitions.
    """

    queryset = ConditionCategory.objects.all()
    serializer_class = ConditionCategorySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None


class CapabilityTypeViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for capability types.

    Read-only endpoint for retrieving capability definitions.
    """

    queryset = CapabilityType.objects.all()
    serializer_class = CapabilityTypeSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None


class CheckTypeViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for check types.

    Read-only endpoint for retrieving check type definitions.
    """

    queryset = CheckType.objects.all()
    serializer_class = CheckTypeSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None


class DamageTypeViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for damage types.

    Read-only endpoint for retrieving damage type definitions.
    """

    queryset = DamageType.objects.all()
    serializer_class = DamageTypeSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None


# =============================================================================
# Condition Template ViewSet
# =============================================================================


class ConditionTemplateViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for condition templates.

    Provides browsing of available condition definitions.
    Used for tooltips, condition browsers, and reference.
    """

    queryset = ConditionTemplate.objects.select_related("category").prefetch_related("stages")
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_serializer_class(self):
        """Use detail serializer for retrieve action."""
        if self.action == "retrieve":
            return ConditionTemplateDetailSerializer
        return ConditionTemplateSerializer

    @action(detail=False, methods=["get"])
    def by_category(self, request: Request) -> Response:
        """
        Get conditions grouped by category.

        Returns a dict mapping category slugs to lists of conditions.
        """
        categories = ConditionCategory.objects.prefetch_related("conditions").order_by(
            "display_order"
        )

        result = {}
        for category in categories:
            conditions = category.conditions.all()
            result[category.name] = {
                "category": ConditionCategorySerializer(category).data,
                "conditions": ConditionTemplateSerializer(conditions, many=True).data,
            }

        return Response(result)


# =============================================================================
# Character Conditions ViewSet
# =============================================================================


def _build_effect_lookups(
    conditions: list[ConditionInstance],
) -> EffectLookups:
    """Build lookup tables for batch-querying condition effects."""
    condition_ids: list[int] = []
    stage_ids: list[int] = []
    instance_by_condition: dict[int, ConditionInstance] = {}
    instance_by_stage: dict[int, ConditionInstance] = {}
    for inst in conditions:
        condition_ids.append(inst.condition_id)
        instance_by_condition[inst.condition_id] = inst
        if inst.current_stage_id:
            stage_ids.append(inst.current_stage_id)
            instance_by_stage[inst.current_stage_id] = inst

    effect_filter = Q(condition_id__in=condition_ids)
    if stage_ids:
        effect_filter |= Q(stage_id__in=stage_ids)

    return EffectLookups(
        effect_filter=effect_filter,
        instance_by_condition=instance_by_condition,
        instance_by_stage=instance_by_stage,
    )


def _resolve_instance(
    effect: ConditionCapabilityEffect | ConditionCheckModifier | ConditionResistanceModifier,
    lookups: EffectLookups,
) -> ConditionInstance | None:
    """Resolve which ConditionInstance an effect row belongs to."""
    return lookups.instance_by_condition.get(effect.condition_id) or lookups.instance_by_stage.get(
        effect.stage_id
    )


def _aggregate_capability_effects(lookups: EffectLookups) -> CapabilitySummary:
    """Batch query capability effects and aggregate into blocked/modifier dicts."""
    summary = CapabilitySummary()
    for effect in ConditionCapabilityEffect.objects.filter(lookups.effect_filter).select_related(
        "capability"
    ):
        inst = _resolve_instance(effect, lookups)
        if not inst:
            continue
        cap_name = effect.capability.name
        if effect.effect_type == CapabilityEffectType.BLOCKED:
            if cap_name not in summary.blocked:
                summary.blocked.append(cap_name)
        elif effect.effect_type in (CapabilityEffectType.REDUCED, CapabilityEffectType.ENHANCED):
            modifier = effect.modifier_percent
            if inst.current_stage:
                modifier = int(modifier * inst.current_stage.severity_multiplier)
            summary.modifiers[cap_name] = summary.modifiers.get(cap_name, 0) + modifier
    summary.modifiers = {k: v for k, v in summary.modifiers.items() if v != 0}
    return summary


def _aggregate_check_modifiers(lookups: EffectLookups) -> dict[str, int]:
    """Batch query check modifiers and aggregate by check type name."""
    result: dict[str, int] = {}
    for mod in ConditionCheckModifier.objects.filter(lookups.effect_filter).select_related(
        "check_type"
    ):
        inst = _resolve_instance(mod, lookups)
        if not inst:
            continue
        modifier_value = mod.modifier_value
        if mod.scales_with_severity:
            modifier_value = modifier_value * inst.effective_severity
        if inst.current_stage:
            modifier_value = int(modifier_value * inst.current_stage.severity_multiplier)
        check_name = mod.check_type.name
        result[check_name] = result.get(check_name, 0) + modifier_value
    return {k: v for k, v in result.items() if v != 0}


def _aggregate_resistance_modifiers(lookups: EffectLookups) -> dict[str, int]:
    """Batch query resistance modifiers and aggregate by damage type name."""
    result: dict[str, int] = {}
    for mod in ConditionResistanceModifier.objects.filter(lookups.effect_filter).select_related(
        "damage_type"
    ):
        inst = _resolve_instance(mod, lookups)
        if not inst:
            continue
        modifier_value = mod.modifier_value
        if inst.current_stage:
            modifier_value = int(modifier_value * inst.current_stage.severity_multiplier)
        if mod.damage_type:
            dtype_name = mod.damage_type.name
            result[dtype_name] = result.get(dtype_name, 0) + modifier_value
    return {k: v for k, v in result.items() if v != 0}


class CharacterConditionsViewSet(CharacterContextMixin, viewsets.ViewSet):
    """
    ViewSet for managing a character's active conditions.

    Provides endpoints for:
    - list: Get character's active conditions
    - summary: Get conditions with all aggregated effects
    - observed: Get conditions visible to observers

    Requires X-Character-ID header to identify which character to operate on.
    Conditions are applied via game logic, not directly through this API.
    """

    permission_classes = [IsAuthenticated]

    def list(self, request: Request) -> Response:
        """
        Get character's active conditions.

        Returns all conditions on the character, sorted by display priority.
        """
        character = self._get_character(request)
        if not character:
            return Response(
                {"detail": "No character found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        conditions = get_active_conditions(character).order_by(
            "-condition__display_priority",
            "condition__category__display_order",
            "condition__name",
        )

        return Response(ConditionInstanceSerializer(conditions, many=True).data)

    @action(detail=False, methods=["get"])
    def summary(self, request: Request) -> Response:
        """
        Get conditions summary with all aggregated effects.

        Returns conditions plus net modifiers for capabilities, checks,
        resistances, turn order, and aggro. This is the primary endpoint
        for the character sheet conditions tab.
        """
        character = self._get_character(request)
        if not character:
            return Response(
                {"detail": "No character found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        conditions = list(
            get_active_conditions(character).order_by(
                "-condition__display_priority",
                "condition__category__display_order",
                "condition__name",
            )
        )

        negative_count = sum(1 for c in conditions if c.condition.category.is_negative)
        positive_count = len(conditions) - negative_count

        # Batch-query all effects in 3 queries instead of N per type
        lookups = _build_effect_lookups(conditions)
        cap_summary = _aggregate_capability_effects(lookups)
        check_modifiers = _aggregate_check_modifiers(lookups)
        resistance_modifiers = _aggregate_resistance_modifiers(lookups)

        turn_order_mod = get_turn_order_modifier(character)
        aggro = get_aggro_priority(character)

        return Response(
            {
                "conditions": ConditionInstanceSerializer(conditions, many=True).data,
                "total_conditions": len(conditions),
                "negative_count": negative_count,
                "positive_count": positive_count,
                "blocked_capabilities": cap_summary.blocked,
                "capability_modifiers": cap_summary.modifiers,
                "check_modifiers": check_modifiers,
                "resistance_modifiers": resistance_modifiers,
                "turn_order_modifier": turn_order_mod,
                "aggro_priority": aggro,
            }
        )

    @action(detail=False, methods=["get"])
    def observed(self, request: Request) -> Response:
        """
        Get conditions visible to observers.

        Used when viewing another character's visible conditions.
        Only returns conditions with is_visible_to_others=True.

        Query params:
            target_id: ID of the character being observed
        """
        target_id = request.query_params.get("target_id")
        if not target_id:
            return Response(
                {"detail": "target_id query parameter required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            target = ObjectDB.objects.get(id=int(target_id))
        except (ValueError, ObjectDB.DoesNotExist):
            return Response(
                {"detail": "Target not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Only show visible conditions
        conditions = (
            get_active_conditions(target)
            .filter(condition__is_visible_to_others=True)
            .order_by(
                "-condition__display_priority",
                "condition__category__display_order",
                "condition__name",
            )
        )

        return Response(ConditionInstanceObserverSerializer(conditions, many=True).data)
