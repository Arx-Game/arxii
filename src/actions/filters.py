"""FilterSets for the actions app."""

from __future__ import annotations

import django_filters

from actions.models import ActionTemplate


class ActionTemplateFilter(django_filters.FilterSet):
    """Filter for ActionTemplate list endpoint."""

    target_type = django_filters.CharFilter(field_name="target_type")

    class Meta:
        model = ActionTemplate
        fields = ["target_type"]
