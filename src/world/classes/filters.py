"""
Classes filters for ViewSets.
"""

from typing import Any

import django_filters

from world.classes.models import Path

_IS_ACTIVE = "is_active"
_TRUE = "true"


class PathFilter(django_filters.FilterSet):
    """Filter paths with default-to-active behavior."""

    stage = django_filters.NumberFilter(field_name="stage")
    is_active = django_filters.BooleanFilter(field_name=_IS_ACTIVE)

    class Meta:
        model = Path
        fields = ["stage", _IS_ACTIVE]

    def __init__(self, data: Any = None, *args: Any, **kwargs: Any) -> None:
        if data is not None:
            data = data.copy()
            if _IS_ACTIVE not in data:
                data[_IS_ACTIVE] = _TRUE
        super().__init__(data, *args, **kwargs)
