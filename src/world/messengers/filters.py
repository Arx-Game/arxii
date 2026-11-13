"""Filters for the missives API (#3289).

``MissiveFilterSet``: both filters read the ``viewer_sent`` annotation
``MissiveViewSet.get_queryset`` puts on every row (``services.sent_by_q`` for the reading
character), so "sent" and "received" follow the same rule as the telnet list and the reply
action.

``MissiveAddresseeFilterSet``: the compose "To" picker's name search over the addressable
faces; a search under two characters is invalid and finds nobody.
"""

from __future__ import annotations

from django.db.models import Q, QuerySet
import django_filters

from world.messengers.constants import MissiveDirection
from world.messengers.models import Missive
from world.scenes.models import Persona

VIEWER_SENT = "viewer_sent"


class MissiveFilterSet(django_filters.FilterSet):
    direction = django_filters.ChoiceFilter(
        choices=MissiveDirection.choices, method="filter_direction"
    )
    unread = django_filters.BooleanFilter(method="filter_unread")

    class Meta:
        model = Missive
        fields = ["direction", "unread"]

    def filter_direction(
        self, queryset: QuerySet[Missive], name: str, value: str
    ) -> QuerySet[Missive]:
        return queryset.filter(**{VIEWER_SENT: value == MissiveDirection.SENT})

    def filter_unread(
        self, queryset: QuerySet[Missive], name: str, value: bool | None
    ) -> QuerySet[Missive]:
        if value is None:
            return queryset
        unread = Q(**{VIEWER_SENT: False}, read_at__isnull=True)
        return queryset.filter(unread) if value else queryset.exclude(unread)


class MissiveAddresseeFilterSet(django_filters.FilterSet):
    search = django_filters.CharFilter(
        field_name="name", lookup_expr="icontains", required=True, min_length=2
    )

    class Meta:
        model = Persona
        fields = ["search"]
