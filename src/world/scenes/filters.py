from django.db.models import QuerySet
from django.utils import timezone
import django_filters

from world.scenes.models import Persona, Scene, SceneMessage


class SceneFilter(django_filters.FilterSet):
    is_active = django_filters.BooleanFilter()
    is_public = django_filters.BooleanFilter()
    location = django_filters.NumberFilter(field_name="location__id")
    participant = django_filters.NumberFilter(field_name="participants__id")
    status = django_filters.CharFilter(method="filter_status")
    gm = django_filters.NumberFilter(method="filter_gm")
    player = django_filters.NumberFilter(method="filter_player")

    class Meta:
        model = Scene
        fields = [
            "is_active",
            "is_public",
            "location",
            "participant",
            "status",
            "gm",
            "player",
        ]

    def filter_status(self, queryset: QuerySet[Scene], name: str, value: str) -> QuerySet[Scene]:
        now = timezone.now()
        if value == "active":
            return queryset.filter(
                is_active=True,
                date_started__lte=now,
                date_finished__isnull=True,
            )
        if value == "completed":
            return queryset.filter(is_active=False, date_finished__isnull=False)
        if value == "upcoming":
            return queryset.filter(is_active=False, date_started__gt=now)
        return queryset

    def filter_gm(self, queryset: QuerySet[Scene], name: str, value: str) -> QuerySet[Scene]:
        return queryset.filter(
            participations__account__id=value,
            participations__is_gm=True,
        ).distinct()

    def filter_player(self, queryset: QuerySet[Scene], name: str, value: str) -> QuerySet[Scene]:
        return queryset.filter(
            participations__account__id=value,
            participations__is_gm=False,
        ).distinct()


class PersonaFilter(django_filters.FilterSet):
    scene = django_filters.NumberFilter(field_name="participation__scene__id")
    participation = django_filters.NumberFilter(field_name="participation__id")
    account = django_filters.NumberFilter(field_name="participation__account__id")
    character = django_filters.NumberFilter(field_name="character__id")

    class Meta:
        model = Persona
        fields = ["scene", "participation", "account", "character"]


class SceneMessageFilter(django_filters.FilterSet):
    scene = django_filters.NumberFilter(field_name="scene__id")
    persona = django_filters.NumberFilter(field_name="persona__id")
    context = django_filters.CharFilter(field_name="context")
    mode = django_filters.CharFilter(field_name="mode")

    class Meta:
        model = SceneMessage
        fields = ["scene", "persona", "context", "mode"]
