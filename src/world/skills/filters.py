"""
Skills filters for ViewSets.
"""

from typing import Any

import django_filters

from world.skills.models import Skill, Specialization

_IS_ACTIVE = "is_active"
_TRUE = "true"


class SkillFilter(django_filters.FilterSet):
    """Filter skills with default-to-active behavior."""

    is_active = django_filters.BooleanFilter(field_name=_IS_ACTIVE)

    class Meta:
        model = Skill
        fields = [_IS_ACTIVE]

    def __init__(self, data: Any = None, *args: Any, **kwargs: Any) -> None:
        if data is not None:
            data = data.copy()
            if _IS_ACTIVE not in data:
                data[_IS_ACTIVE] = _TRUE
        super().__init__(data, *args, **kwargs)


class SpecializationFilter(django_filters.FilterSet):
    """Filter specializations with default-to-active behavior."""

    parent_skill = django_filters.NumberFilter(field_name="parent_skill")
    is_active = django_filters.BooleanFilter(field_name=_IS_ACTIVE)

    class Meta:
        model = Specialization
        fields = ["parent_skill", _IS_ACTIVE]

    def __init__(self, data: Any = None, *args: Any, **kwargs: Any) -> None:
        if data is not None:
            data = data.copy()
            if _IS_ACTIVE not in data:
                data[_IS_ACTIVE] = _TRUE
        super().__init__(data, *args, **kwargs)
