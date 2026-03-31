from django.db.models import QuerySet
import django_filters

from world.events.constants import EventStatus
from world.events.models import Event, EventInvitation
from world.societies.models import Organization, Society


class EventFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="status")
    is_public = django_filters.BooleanFilter(field_name="is_public")
    location = django_filters.NumberFilter(field_name="location_id")
    host = django_filters.NumberFilter(method="filter_host")
    upcoming = django_filters.BooleanFilter(method="filter_upcoming")

    class Meta:
        model = Event
        fields = ["status", "is_public", "location", "host", "upcoming"]

    def filter_host(self, queryset: QuerySet[Event], name: str, value: int) -> QuerySet[Event]:
        return queryset.filter(hosts__persona_id=value).distinct()

    def filter_upcoming(self, queryset: QuerySet[Event], name: str, value: bool) -> QuerySet[Event]:
        # Currently only matches SCHEDULED status. Future: may include DRAFT
        # for the event's own hosts.
        if value:
            return queryset.filter(status=EventStatus.SCHEDULED)
        return queryset


class EventInvitationFilter(django_filters.FilterSet):
    event = django_filters.NumberFilter(field_name="event_id")

    class Meta:
        model = EventInvitation
        fields = ["event"]


class OrganizationSearchFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(field_name="name", lookup_expr="icontains")

    class Meta:
        model = Organization
        fields = ["search"]


class SocietySearchFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(field_name="name", lookup_expr="icontains")

    class Meta:
        model = Society
        fields = ["search"]
