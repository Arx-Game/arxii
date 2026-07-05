"""Filters for the companions API (#672)."""

from __future__ import annotations

import django_filters

from world.companions.models import Companion


class CompanionFilterSet(django_filters.FilterSet):
    class Meta:
        model = Companion
        fields = ["archetype__domain"]
