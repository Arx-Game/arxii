"""FilterSets for the tasking API."""

import django_filters

from world.assets.models import NPCAsset
from world.tasking.models import OrgTask, TaskOutcomeRoute, TaskTemplate


class TaskTemplateFilterSet(django_filters.FilterSet):
    category = django_filters.CharFilter(field_name="category")
    is_active = django_filters.BooleanFilter(field_name="is_active")
    name = django_filters.CharFilter(field_name="name", lookup_expr="icontains")

    class Meta:
        model = TaskTemplate
        fields: list[str] = []


class TaskOutcomeRouteFilterSet(django_filters.FilterSet):
    template = django_filters.NumberFilter(field_name="template_id")

    class Meta:
        model = TaskOutcomeRoute
        fields: list[str] = []


class OrgRosterFilterSet(django_filters.FilterSet):
    org = django_filters.NumberFilter(field_name="promoter_org_id")

    class Meta:
        model = NPCAsset
        fields: list[str] = []


class OrgTaskFilterSet(django_filters.FilterSet):
    org = django_filters.NumberFilter(field_name="org_id")
    status = django_filters.CharFilter(field_name="status")
    category = django_filters.CharFilter(field_name="template__category")

    class Meta:
        model = OrgTask
        fields: list[str] = []
