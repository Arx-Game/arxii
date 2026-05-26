"""django-filter FilterSets for the missions API.

Per the project's "Always use django-filter FilterSet classes for query
parameter handling in ViewSets and Views" rule (custom linter enforced),
ViewSets must never read request.query_params directly. Each filter
exposes a structured query surface for the authoring tool.

D1 ships ``MissionTemplateFilterSet`` (browse). Additional FilterSets
for editor CRUD and giver library land in D2/D3.
"""

from django.db.models import QuerySet
import django_filters

from world.missions.constants import AccessTier, ArcScope
from world.missions.models import (
    MissionGiver,
    MissionGiverOffering,
    MissionGiverStanding,
    MissionNode,
    MissionOption,
    MissionOptionRoute,
    MissionOptionRouteCandidate,
    MissionOptionRouteReward,
    MissionTemplate,
)


class MissionTemplateFilterSet(django_filters.FilterSet):
    """Filters for the MissionTemplateViewSet browse endpoint.

    Plan-defined surface: name (substring), level band, area (giver→
    room→Area; deferred — see DESIGN below), category (by name), risk,
    org (giver's org by name), status (is_active / arc_scope / access_tier).
    """

    name = django_filters.CharFilter(field_name="name", lookup_expr="icontains")
    # Level-band filters — the template's band is a [min, max] range; we
    # let the operator filter on either bound or assert "applies to level
    # X" with `level_band_contains=X`.
    level_band_min = django_filters.NumberFilter(field_name="level_band_min")
    level_band_max = django_filters.NumberFilter(field_name="level_band_max")
    level_band_contains = django_filters.NumberFilter(method="filter_level_band_contains")
    risk_tier = django_filters.NumberFilter(field_name="risk_tier")
    is_active = django_filters.BooleanFilter(field_name="is_active")
    arc_scope = django_filters.ChoiceFilter(field_name="arc_scope", choices=ArcScope.choices)
    access_tier = django_filters.ChoiceFilter(field_name="access_tier", choices=AccessTier.choices)
    category = django_filters.CharFilter(field_name="categories__name", lookup_expr="iexact")
    org = django_filters.CharFilter(
        field_name="givers__org__name", lookup_expr="iexact", distinct=True
    )

    # DESIGN: the plan calls out an "area" filter (giver → target room →
    # locations.RoomProfile → areas.Area). That is a 4-hop chain and the
    # giver target FK is to ObjectDB (typeclass discriminates room vs
    # other). Punting until D3 lands the giver library and validates the
    # most ergonomic shape — likely a `giver_area_slug` filter exposing
    # the materialized AreaClosure view for ancestor-aware matching.

    class Meta:
        model = MissionTemplate
        fields: list[str] = []  # all real filters defined explicitly above

    @staticmethod
    def filter_level_band_contains(
        queryset: QuerySet[MissionTemplate],
        name: str,  # noqa: ARG004 — FilterSet method signature requires it
        value: int,
    ) -> QuerySet[MissionTemplate]:
        """Match templates whose [min, max] band contains the given level."""
        return queryset.filter(level_band_min__lte=value, level_band_max__gte=value)


# ---------------------------------------------------------------------------
# D2 editor CRUD filters — each nested viewset filters on its parent FK
# (template/node/option/route) plus any other useful editor query
# surfaces (e.g. is_entry on nodes, source_kind on options).
# ---------------------------------------------------------------------------


class MissionNodeFilterSet(django_filters.FilterSet):
    """Filter MissionNode rows by template + entry-flag + flavor-flag.

    ``needs_rewrite`` is the per-author "flavor inherited from a copy still
    needs editing" flag; the E6 needs-rewrite queue uses it.
    """

    template = django_filters.NumberFilter(field_name="template_id")
    template_slug = django_filters.CharFilter(field_name="template__slug")
    is_entry = django_filters.BooleanFilter(field_name="is_entry")
    needs_rewrite = django_filters.BooleanFilter(field_name="flavor_text_needs_rewrite")

    class Meta:
        model = MissionNode
        fields: list[str] = []


class MissionOptionFilterSet(django_filters.FilterSet):
    """Filter MissionOption rows by node / source_kind / option_kind + flavor-flag."""

    node = django_filters.NumberFilter(field_name="node_id")
    template = django_filters.NumberFilter(field_name="node__template_id")
    source_kind = django_filters.CharFilter(field_name="source_kind")
    option_kind = django_filters.CharFilter(field_name="option_kind")
    needs_rewrite = django_filters.BooleanFilter(field_name="authored_ic_framing_needs_rewrite")

    class Meta:
        model = MissionOption
        fields: list[str] = []


class MissionOptionRouteFilterSet(django_filters.FilterSet):
    """Filter MissionOptionRoute rows by option / template / outcome tier + flavor-flag."""

    option = django_filters.NumberFilter(field_name="option_id")
    template = django_filters.NumberFilter(field_name="option__node__template_id")
    outcome_tier = django_filters.NumberFilter(field_name="outcome_tier_id")
    is_random_set = django_filters.BooleanFilter(field_name="is_random_set")
    needs_rewrite = django_filters.BooleanFilter(field_name="outcome_text_needs_rewrite")

    class Meta:
        model = MissionOptionRoute
        fields: list[str] = []


class MissionOptionRouteCandidateFilterSet(django_filters.FilterSet):
    """Filter MissionOptionRouteCandidate rows by route / template."""

    route = django_filters.NumberFilter(field_name="route_id")
    template = django_filters.NumberFilter(field_name="route__option__node__template_id")

    class Meta:
        model = MissionOptionRouteCandidate
        fields: list[str] = []


class MissionOptionRouteRewardFilterSet(django_filters.FilterSet):
    """Filter MissionOptionRouteReward rows by route or candidate parent."""

    route = django_filters.NumberFilter(field_name="route_id")
    candidate = django_filters.NumberFilter(field_name="candidate_id")
    kind = django_filters.CharFilter(field_name="kind")
    sink = django_filters.CharFilter(field_name="sink")

    class Meta:
        model = MissionOptionRouteReward
        fields: list[str] = []


# ---------------------------------------------------------------------------
# D3 giver-library filters.
# ---------------------------------------------------------------------------


class MissionGiverFilterSet(django_filters.FilterSet):
    """Filter MissionGiver rows by org / kind / active / name substring."""

    name = django_filters.CharFilter(field_name="name", lookup_expr="icontains")
    giver_kind = django_filters.CharFilter(field_name="giver_kind")
    org = django_filters.NumberFilter(field_name="org_id")
    org_name = django_filters.CharFilter(field_name="org__name", lookup_expr="iexact")
    is_active = django_filters.BooleanFilter(field_name="is_active")

    class Meta:
        model = MissionGiver
        fields: list[str] = []


class MissionGiverOfferingFilterSet(django_filters.FilterSet):
    """Filter MissionGiverOffering rows by giver / template."""

    giver = django_filters.NumberFilter(field_name="giver_id")
    giver_slug = django_filters.CharFilter(field_name="giver__slug")
    template = django_filters.NumberFilter(field_name="template_id")
    template_slug = django_filters.CharFilter(field_name="template__slug")

    class Meta:
        model = MissionGiverOffering
        fields: list[str] = []


class MissionGiverStandingFilterSet(django_filters.FilterSet):
    """Filter MissionGiverStanding rows by giver / character.

    Affection-range queries are rarely useful at the API surface (staff
    just navigates to a specific (giver, character) pair); supporting
    them later as ``min_affection`` / ``max_affection`` is trivial.
    """

    giver = django_filters.NumberFilter(field_name="giver_id")
    giver_slug = django_filters.CharFilter(field_name="giver__slug")
    character = django_filters.NumberFilter(field_name="character_id")

    class Meta:
        model = MissionGiverStanding
        fields: list[str] = []
