"""DRF viewsets for the flows authoring API (#3417 task 4).

``DslCatalogViewSet`` hands the frontend authoring palette the full DSL
surface (actions, events, service functions, filter ops, variable-name
roles) in one call. ``FlowDefinitionViewSet`` is CRUD on ``FlowDefinition``
rows, with step-tree writes delegated to ``flows.serializers``.
"""

from collections.abc import Iterable
import dataclasses

from django.db.models import Count, Prefetch, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from evennia.objects.models import ObjectDB
from rest_framework import viewsets
from rest_framework.filters import SearchFilter
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission, IsAdminUser, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from flows.catalog import (
    FILTER_OPS,
    STEP_ACTION_SPECS,
    VariableNameRole,
    event_catalog,
    service_function_catalog,
)
from flows.consts import FlowActionChoices
from flows.models import FlowDefinition, FlowStepDefinition, Trigger, TriggerDefinition
from flows.serializers import (
    FlowDefinitionDetailSerializer,
    FlowDefinitionListSerializer,
    FlowDefinitionWriteSerializer,
    TriggerDefinitionSerializer,
    TriggerSerializer,
)
from world.gm.permissions import IsGMOrStaff


class DslCatalogViewSet(viewsets.ViewSet):
    """Read-only DSL authoring catalog for the flows authoring palette.

    Returns everything the frontend needs to render the step palette and
    per-step editors without hard-coding the DSL surface: every step action
    (with its param schema), every event (with its payload fields), every
    registered service function (with its param types), the comparison
    operators available to filter conditions, and the ``variable_name``
    roles a step's action can assign.
    """

    permission_classes = [IsAuthenticated, IsGMOrStaff]

    def list(self, request: Request) -> Response:
        actions = [
            dataclasses.asdict(STEP_ACTION_SPECS[value])
            for value, _label in FlowActionChoices.choices
            if value in STEP_ACTION_SPECS
        ]
        return Response(
            {
                "actions": actions,
                "events": event_catalog(),
                "service_functions": service_function_catalog(),
                "filter_ops": list(FILTER_OPS),
                "variable_name_roles": [role.value for role in VariableNameRole],
            }
        )


class StaffWriteGMReadPermissionMixin:
    """Staff or GM can read (list/retrieve); only staff can write.

    Shared by every authoring viewset that GMs should be able to browse but
    not edit (flow definitions here; trigger definitions in a later task).
    """

    def get_permissions(self) -> list[BasePermission]:
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated(), IsGMOrStaff()]
        return [IsAuthenticated(), IsAdminUser()]


class FlowAuthoringPagination(PageNumberPagination):
    """Shared pagination for the flows authoring API."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class FlowDefinitionViewSet(StaffWriteGMReadPermissionMixin, viewsets.ModelViewSet):
    """Staff-write / GM-read CRUD on ``FlowDefinition`` rows.

    List rows are lightweight (id/name/description/step_count, the latter
    from an annotated ``Count`` rather than a per-row query); retrieve
    returns the full step tree in depth-first authored order (steps are
    always inserted depth-first by ``flows.serializers._replace_steps`, and
    fetched here in explicit pk order for the same reason: stable ordering
    should never depend on undocumented default-table-scan order).
    """

    pagination_class = FlowAuthoringPagination
    filter_backends = [SearchFilter]
    search_fields = ["name", "description"]

    def get_queryset(self) -> QuerySet[FlowDefinition]:
        queryset = FlowDefinition.objects.all().order_by("pk")
        if self.action == "retrieve":
            return queryset.prefetch_related(
                Prefetch(
                    "steps",
                    queryset=FlowStepDefinition.objects.order_by("pk"),
                    to_attr="prefetched_steps",
                )
            )
        return queryset.annotate(step_count=Count("steps"))

    def get_serializer_class(self) -> type[BaseSerializer[FlowDefinition]]:
        if self.action == "retrieve":
            return FlowDefinitionDetailSerializer
        if self.action == "list":
            return FlowDefinitionListSerializer
        return FlowDefinitionWriteSerializer


def _invalidate_trigger_owners(objs: Iterable[ObjectDB]) -> None:
    """Drop each object's cached triggers, as the game's own trigger writers do (#4800).

    An object loads its triggers once and keeps them, so an authored change reaches
    it only once its handler is told; otherwise it waits for a server restart.
    """
    for obj in {obj.pk: obj for obj in objs}.values():
        obj.trigger_handler.invalidate()


class TriggerDefinitionViewSet(StaffWriteGMReadPermissionMixin, viewsets.ModelViewSet):
    """Staff-write / GM-read CRUD on ``TriggerDefinition`` rows (#3417 task 6)."""

    queryset = TriggerDefinition.objects.all().order_by("pk")
    serializer_class = TriggerDefinitionSerializer
    pagination_class = FlowAuthoringPagination
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["event_name"]
    search_fields = ["name"]

    def perform_update(self, serializer: BaseSerializer[TriggerDefinition]) -> None:
        definition = serializer.save()
        # The event a definition listens for decides where its triggers are cached.
        _invalidate_trigger_owners(
            trigger.obj for trigger in definition.trigger_set.select_related("obj")
        )

    def perform_destroy(self, instance: TriggerDefinition) -> None:
        # Deleting a definition takes its triggers with it.
        owners = [trigger.obj for trigger in instance.trigger_set.select_related("obj")]
        instance.delete()
        _invalidate_trigger_owners(owners)


class TriggerViewSet(StaffWriteGMReadPermissionMixin, viewsets.ModelViewSet):
    """Staff-write / GM-read CRUD on ``Trigger`` rows (#3417 task 6).

    A ``Trigger`` installs a ``TriggerDefinition`` on a specific object.
    """

    queryset = Trigger.objects.all().select_related("trigger_definition").order_by("pk")
    serializer_class = TriggerSerializer
    pagination_class = FlowAuthoringPagination
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["trigger_definition", "obj"]
    search_fields = ["trigger_definition__name"]

    def perform_create(self, serializer: BaseSerializer[Trigger]) -> None:
        trigger = serializer.save()
        _invalidate_trigger_owners([trigger.obj])

    def perform_update(self, serializer: BaseSerializer[Trigger]) -> None:
        previous_obj = serializer.instance.obj
        trigger = serializer.save()
        _invalidate_trigger_owners([previous_obj, trigger.obj])

    def perform_destroy(self, instance: Trigger) -> None:
        obj = instance.obj
        instance.delete()
        _invalidate_trigger_owners([obj])
