"""Cached access to a persona's common-knowledge deeds for the legend murmur (#2523).

The handler is the data source for legend-murmur ``AmbientEmoteLine`` dynamic
bodies — it does not deliver messages itself. Delivery rides #2471's existing
MOVED Trigger+Flow -> ``deliver_ambient_group`` -> ``_deliver_line`` pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils.functional import cached_property

if TYPE_CHECKING:
    from world.scenes.models import Persona


class PersonaLegendMurmurHandler:
    """Cached access to a persona's common-knowledge, non-secret deeds (#2523).

    Computed once per ``Persona`` instance and invalidated at the mutation
    points (deed created/spread, secret linked, deed deactivated) via
    ``CachedPropertiesMixin`` on ``Persona``.
    """

    def __init__(self, persona: Persona) -> None:
        self.persona = persona

    @cached_property
    def murmurable_deeds(self) -> list:
        """The persona's common-knowledge deeds without a linked ``Secret``.

        Mirrors the anonymous-viewer branch of ``_build_card_visible_deeds``
        (``renown_serializers.py:351``) -- common-knowledge (spread >= 5x base),
        no explaining ``Secret``, active, ordered by spread desc then recency.
        """
        from django.db.models import F, Sum  # noqa: PLC0415
        from django.db.models.functions import Coalesce  # noqa: PLC0415

        from world.societies.constants import COMMON_KNOWLEDGE_MULTIPLIER  # noqa: PLC0415
        from world.societies.models import LegendEntry  # noqa: PLC0415

        return list(
            LegendEntry.objects.filter(persona=self.persona, is_active=True)
            .exclude(explaining_secrets__isnull=False)
            .annotate(spread_total=Coalesce(Sum("spreads__value_added"), 0))
            .filter(
                base_value__gt=0,
                spread_total__gte=(COMMON_KNOWLEDGE_MULTIPLIER - 1) * F("base_value"),
            )
            .order_by("-spread_total", "-created_at")
        )

    @cached_property
    def has_murmurable_deeds(self) -> bool:
        """True if any murmurable deeds exist -- the ``LEGEND_DEED`` condition gate."""
        return bool(self.murmurable_deeds)

    @cached_property
    def deed_titles(self) -> list[str]:
        """Top 3 deed titles for body templating."""
        return [deed.title for deed in self.murmurable_deeds[:3]]
