from django.db.models import QuerySet
from django.utils import timezone
import django_filters

from world.scenes.constants import SceneStatus
from world.scenes.models import Persona, Scene, SceneSummaryRevision


class SceneFilter(django_filters.FilterSet):
    is_active = django_filters.BooleanFilter()
    privacy_mode = django_filters.CharFilter(field_name="privacy_mode")
    location = django_filters.NumberFilter(field_name="location__id")
    participant = django_filters.NumberFilter(field_name="participants__id")
    status = django_filters.CharFilter(method="filter_status")
    gm = django_filters.NumberFilter(method="filter_gm")
    player = django_filters.NumberFilter(method="filter_player")

    class Meta:
        model = Scene
        fields = [
            "is_active",
            "privacy_mode",
            "location",
            "participant",
            "status",
            "gm",
            "player",
        ]

    def filter_status(self, queryset: QuerySet[Scene], name: str, value: str) -> QuerySet[Scene]:
        now = timezone.now()
        if value == SceneStatus.ACTIVE:
            return queryset.filter(
                is_active=True,
                date_started__lte=now,
                date_finished__isnull=True,
            )
        if value == SceneStatus.COMPLETED:
            return queryset.filter(is_active=False, date_finished__isnull=False)
        if value == SceneStatus.UPCOMING:
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
    scene = django_filters.NumberFilter(field_name="interactions_written__scene__id", distinct=True)
    character = django_filters.NumberFilter(field_name="character_sheet__character__id")
    character_sheet = django_filters.NumberFilter(field_name="character_sheet__id")
    persona_type = django_filters.CharFilter(field_name="persona_type")

    class Meta:
        model = Persona
        fields = ["scene", "character", "character_sheet", "persona_type"]


class SceneSummaryRevisionFilter(django_filters.FilterSet):
    scene = django_filters.NumberFilter(field_name="scene_id")

    class Meta:
        model = SceneSummaryRevision
        fields = ["scene"]
