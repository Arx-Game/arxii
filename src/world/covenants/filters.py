"""FilterSet classes for covenants API."""

from django.db.models import QuerySet
import django_filters

from world.covenants.models import (
    CharacterCovenantRole,
    Covenant,
    CovenantRite,
    CovenantRole,
    GearArchetypeCompatibility,
)


class CovenantRoleFilter(django_filters.FilterSet):
    """Filter covenant roles by covenant type."""

    class Meta:
        model = CovenantRole
        fields = ["covenant_type"]


class CharacterCovenantRoleFilter(django_filters.FilterSet):
    """Filter character covenant role assignments."""

    is_active = django_filters.BooleanFilter(
        field_name="left_at",
        lookup_expr="isnull",
        help_text="True returns active assignments only; False returns ended only.",
    )

    class Meta:
        model = CharacterCovenantRole
        fields = ["character_sheet", "covenant_role", "is_active"]


class CovenantFilter(django_filters.FilterSet):
    """Filter covenants by type and lifecycle state."""

    is_active = django_filters.BooleanFilter(method="filter_is_active")

    class Meta:
        model = Covenant
        fields = ["covenant_type", "is_active"]

    def filter_is_active(
        self, queryset: QuerySet[Covenant], name: str, value: bool
    ) -> QuerySet[Covenant]:
        if value is True:
            return queryset.filter(dissolved_at__isnull=True)
        if value is False:
            return queryset.filter(dissolved_at__isnull=False)
        return queryset


class CovenantRiteFilter(django_filters.FilterSet):
    """Filter covenant rites by covenant type."""

    class Meta:
        model = CovenantRite
        fields = ["covenant_type"]


class GearArchetypeCompatibilityFilter(django_filters.FilterSet):
    """Filter compatibility rows by role or archetype."""

    class Meta:
        model = GearArchetypeCompatibility
        fields = ["covenant_role", "gear_archetype"]
