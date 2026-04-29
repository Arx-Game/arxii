"""FilterSet classes for covenants API."""

import django_filters

from world.covenants.models import GearArchetypeCompatibility


class GearArchetypeCompatibilityFilter(django_filters.FilterSet):
    """Filter compatibility rows by role or archetype."""

    class Meta:
        model = GearArchetypeCompatibility
        fields = ["covenant_role", "gear_archetype"]
