"""Filters for the magic system API."""

from django.db.models import QuerySet
import django_filters
from rest_framework.exceptions import ValidationError

from world.magic.models import Cantrip


class CantripFilter(django_filters.FilterSet):
    """Filter for Cantrip list views."""

    path_id = django_filters.NumberFilter(method="filter_by_path")

    class Meta:
        model = Cantrip
        fields = ["path_id"]

    def filter_by_path(
        self, queryset: QuerySet[Cantrip], name: str, value: int
    ) -> QuerySet[Cantrip]:
        """Filter cantrips by path's allowed styles."""
        from world.classes.models import Path  # noqa: PLC0415

        try:
            Path.objects.get(pk=value, is_active=True)
        except (Path.DoesNotExist, ValueError, TypeError):
            raise ValidationError({"path_id": "Invalid or inactive path."}) from None
        return queryset.filter(style__allowed_paths__id=value)
