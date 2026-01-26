"""
API views for conditions system.

Provides read-only endpoints for:
- Lookup data (categories, damage types, capabilities, check types)
- Condition templates (browsing available conditions)
- Active conditions on characters (for character sheet)
- Condition summaries with aggregated effects
"""

from evennia.objects.models import ObjectDB
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from web.api.mixins import CharacterContextMixin
from world.conditions.models import (
    CapabilityType,
    CheckType,
    ConditionCategory,
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
    get_capability_status,
    get_check_modifier,
    get_resistance_modifier,
    get_turn_order_modifier,
)

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

        # Count by type
        negative_count = sum(1 for c in conditions if c.condition.category.is_negative)
        positive_count = len(conditions) - negative_count

        # Aggregate capability effects
        blocked_capabilities = []
        capability_modifiers = {}
        for cap in CapabilityType.objects.all():
            cap_status = get_capability_status(character, cap)
            if cap_status.is_blocked:
                blocked_capabilities.append(cap.name)
            elif cap_status.modifier_percent != 0:
                capability_modifiers[cap.name] = cap_status.modifier_percent

        # Aggregate check modifiers
        check_modifiers = {}
        for check in CheckType.objects.all():
            result = get_check_modifier(character, check)
            if result.total_modifier != 0:
                check_modifiers[check.name] = result.total_modifier

        # Aggregate resistance modifiers
        resistance_modifiers = {}
        for dtype in DamageType.objects.all():
            result = get_resistance_modifier(character, dtype)
            if result.total_modifier != 0:
                resistance_modifiers[dtype.name] = result.total_modifier

        # Get combat modifiers
        turn_order_mod = get_turn_order_modifier(character)
        aggro = get_aggro_priority(character)

        return Response(
            {
                "conditions": ConditionInstanceSerializer(conditions, many=True).data,
                "total_conditions": len(conditions),
                "negative_count": negative_count,
                "positive_count": positive_count,
                "blocked_capabilities": blocked_capabilities,
                "capability_modifiers": capability_modifiers,
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
