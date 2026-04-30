"""FilterSet classes for covenants API."""

import django_filters

from world.covenants.models import CharacterCovenantRole, GearArchetypeCompatibility


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


class GearArchetypeCompatibilityFilter(django_filters.FilterSet):
    """Filter compatibility rows by role or archetype."""

    class Meta:
        model = GearArchetypeCompatibility
        fields = ["covenant_role", "gear_archetype"]
