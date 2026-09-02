"""FilterSets for the assets API (#3561 stakes ASSET-subject search)."""

from __future__ import annotations

import django_filters

from world.assets.models import NPCAsset


class NPCAssetFilter(django_filters.FilterSet):
    """Name search over the promoted NPC's persona name.

    Backs the stakes-editor ASSET subject picker (#3561): a GM typing a name
    to find the NPCAsset a stake wagers. Icontains, not exact - callers are
    typing partial names, same convention as the society/organization search
    endpoints `SubjectRefFields` already reuses.
    """

    name = django_filters.CharFilter(field_name="asset_persona__name", lookup_expr="icontains")

    class Meta:
        model = NPCAsset
        fields: list[str] = []
