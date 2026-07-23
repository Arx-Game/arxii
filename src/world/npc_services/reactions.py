"""Banded NPC reaction lines (#2632) — data-authored, never per-NPC code.

An NPC reacting to the character they serve ("Alphonso sees to <name>,
admiring them as if they were a work of art") is a row, not a handler:
``NPCReactionLine`` bands on a ``ReactionMetric`` of the served character,
and the metric resolves through ``METRIC_RESOLVERS`` — one function per
metric, shared by every role and placement.

Precedence: a functionary with ANY lines for a metric replaces the role's
set for that metric wholesale (Alphonso's voice, not a mix). Band selection
is the highest ``band_floor`` <= value, mirroring the affection→pool-count
band walk.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from world.npc_services.constants import ReactionMetric

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.npc_services.models import Functionary, NPCRole

#: The 'allure' ModifierTarget name — the social-hotness axis
#: (seeded by world.seeds.social_relationships; Attractive ranks feed it).
ALLURE_TARGET_NAME = "allure"

NAME_TOKEN = "<name>"  # noqa: S105 — template interpolation token, not a secret


def _resolve_allure(sheet: CharacterSheet) -> int:
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415
    from world.mechanics.services import get_modifier_total  # noqa: PLC0415

    target = ModifierTarget.objects.filter(name=ALLURE_TARGET_NAME).first()
    if target is None:
        return 0
    return get_modifier_total(sheet, target)


METRIC_RESOLVERS: dict[str, Callable[[CharacterSheet], int]] = {
    ReactionMetric.ALLURE.value: _resolve_allure,
}


def reaction_line_for(
    *,
    role: NPCRole,
    functionary: Functionary | None,
    metric: str,
    sheet: CharacterSheet,
    name: str,
) -> str | None:
    """The banded reaction line for serving ``sheet``, or None when unauthored.

    ``name`` is the served character's PRESENTED name — the caller resolves
    it (persona-aware); this function only formats.
    """
    from world.npc_services.models import NPCReactionLine  # noqa: PLC0415

    resolver = METRIC_RESOLVERS.get(metric)
    if resolver is None:
        return None
    value = resolver(sheet)

    lines = NPCReactionLine.objects.filter(role=role, metric=metric)
    if functionary is not None and lines.filter(functionary=functionary).exists():
        lines = lines.filter(functionary=functionary)
    else:
        lines = lines.filter(functionary__isnull=True)

    best = lines.filter(band_floor__lte=value).order_by("-band_floor").first()
    if best is None:
        return None
    return best.template.replace(NAME_TOKEN, name)
