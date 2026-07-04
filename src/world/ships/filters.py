"""FilterSet classes for the ships API (#1832 Task 10)."""

from __future__ import annotations

import django_filters

from world.ships.models import ShipDetails


class ShipDetailsFilterSet(django_filters.FilterSet):
    """Filters for the "my ships" list endpoint."""

    class Meta:
        model = ShipDetails
        fields = ["ship_type", "needs_repair"]
