"""
Filters for conditions API ViewSets.
"""

import django_filters

from world.conditions.models import ConditionInstance


class ObservedConditionFilter(django_filters.FilterSet):
    """
    Filter for observed conditions endpoint.

    Supports filtering by:
    - target_id: ID of the character being observed
    """

    target_id = django_filters.NumberFilter(field_name="target_id")

    class Meta:
        model = ConditionInstance
        fields = ["target_id"]
