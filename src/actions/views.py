"""ViewSets for the actions app."""

from __future__ import annotations

from django.db.models import QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated

from actions.filters import ActionTemplateFilter
from actions.models import ActionTemplate
from actions.serializers import ActionTemplateSerializer


class ActionTemplatePagination(PageNumberPagination):
    """Pagination for ActionTemplate list."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 100


class ActionTemplateViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only endpoint for ActionTemplate lookup data."""

    serializer_class = ActionTemplateSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = ActionTemplateFilter
    filter_backends = [DjangoFilterBackend]
    pagination_class = ActionTemplatePagination

    def get_queryset(self) -> QuerySet[ActionTemplate]:
        return ActionTemplate.objects.select_related("check_type").order_by("name")
