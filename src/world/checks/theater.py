"""Resolution theater (#924): dramatic check outcomes feed the roulette wheel.

PR #271 built a complete frontend pipeline — RouletteModal/RouletteWheel,
Redux slice, the ``roulette_result`` WebSocket message, all mounted and
listening — and no backend ever emitted into it. This module is the missing
emitter.

Doctrine (economy umbrella #923, "perceived > actual"): wins should feel
more dangerous than they were. The wheel shows the tier's REAL candidate
faces — Death may scroll past even when character-loss filtering protected
the roller — and lands on the selected outcome. Routine checks stay quiet:
theater fires only when the tier pool contains a ``character_loss``
candidate or an authored ``theater``-flagged consequence.

Failure to deliver theater never breaks resolution — the wheel is garnish,
the outcome is the meal.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from world.checks.models import Consequence

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.checks.types import CheckResult


def should_emit_theater(consequences: list[Consequence]) -> bool:
    """A tier pool is wheel-worthy when real stakes (or authored drama) are on it."""
    return any(c.character_loss or c.theater for c in consequences)


def build_roulette_payload(
    *,
    title: str,
    consequences: list[Consequence],
    selected: Consequence,
) -> dict:
    """Shape the tier candidates into the frontend RoulettePayload contract.

    Matches ``frontend/src/components/roulette/types.ts`` exactly:
    ``{template_name, consequences: [{label, tier_name, weight, is_selected}]}``.
    Identity comparison picks the selected face (tier candidates may include
    unsaved synthetic rows, so pk equality is not reliable).
    """
    return {
        "template_name": title,
        "consequences": [
            {
                "label": c.label,
                "tier_name": c.outcome_tier.name,
                "weight": c.weight,
                "is_selected": c is selected,
            }
            for c in consequences
        ],
    }


def check_outcome_faces(
    check_result: CheckResult,
) -> tuple[list[Consequence], Consequence | None]:
    """Build success-level wheel faces straight off the check's ResultChart bands.

    One unsaved ``Consequence`` face per ``ResultChartOutcome`` row on
    ``check_result.chart`` (ordered by ``min_roll``): ``outcome_tier=row.outcome``,
    ``label=row.outcome.name``, ``weight=row.max_roll - row.min_roll + 1``,
    ``character_loss=False``. The selected face is the one whose outcome matches
    ``check_result.outcome`` (compared by pk).

    HARD RULE (#3807 Part B): faces are read ONLY from the chart's authored bands.
    Never read ``get_rollmod()``, ``effective_roll``, or any outcome-guarantee
    logic (``perform_check`` step 7, ADR-0152) here — the wheel shows the raw
    chart and lands on whatever the backend actually resolved, never a
    rollmod-shaped or guarantee-shaped view of it.

    When ``check_result.outcome`` is not one of the chart's own bands (an outcome
    guarantee lifted the result off this chart), the guaranteed outcome is
    appended as its own weight-1 face and selected — the wheel still shows where
    the roll actually landed even though the chart never authored that band.

    Returns ``([], None)`` when there is no chart or no outcome to build faces from.
    """
    chart = check_result.chart
    outcome = check_result.outcome
    if chart is None or outcome is None:
        return [], None

    faces: list[Consequence] = []
    selected: Consequence | None = None
    for row in chart.outcomes.order_by("min_roll"):
        face = Consequence(
            outcome_tier=row.outcome,
            label=row.outcome.name,
            weight=row.max_roll - row.min_roll + 1,
            character_loss=False,
        )
        faces.append(face)
        if row.outcome_id == outcome.pk:
            selected = face

    if selected is None:
        face = Consequence(
            outcome_tier=outcome,
            label=outcome.name,
            weight=1,
            character_loss=False,
        )
        faces.append(face)
        selected = face

    return faces, selected


def maybe_emit_resolution_theater(
    *,
    character: ObjectDB,  # noqa: OBJECTDB_PARAM - theater targets whoever rolled, any puppet
    title: str,
    consequences: list[Consequence],
    selected: Consequence | None,
    force: bool = False,
) -> bool:
    """Emit the roulette reveal to the roller's client when the pool warrants it.

    Returns True when a payload was actually delivered. Never raises —
    a dead session, missing msg(), or serialization hiccup silently skips
    the garnish.
    """
    if selected is None or not consequences:
        return False
    if not force and not should_emit_theater(consequences):
        return False
    payload = build_roulette_payload(title=title, consequences=consequences, selected=selected)
    try:
        character.msg(roulette_result=((), payload))
    except Exception:  # noqa: BLE001 — theater must never break resolution
        logger.debug("roulette payload delivery failed", exc_info=True)
        return False
    return True
