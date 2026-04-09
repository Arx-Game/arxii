"""Filters for combat API endpoints."""

import django_filters

from world.combat.models import CombatEncounter


class CombatEncounterFilter(django_filters.FilterSet):
    """Filter combat encounters by scene and status."""

    scene = django_filters.NumberFilter(field_name="scene_id")
    status = django_filters.CharFilter(field_name="status")

    class Meta:
        model = CombatEncounter
        fields = ["scene", "status"]
