"""Filters for the missives API (#3289).

Both filters read the ``viewer_sent`` annotation ``MissiveViewSet.get_queryset`` puts on
every row (``services.sent_by_q`` for the reading character), so "sent" and "received"
follow the same rule as the telnet list and the reply action.
"""

from __future__ import annotations

from django.db.models import Q, QuerySet
import django_filters

from world.messengers.constants import MissiveDirection
from world.messengers.models import Missive

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
