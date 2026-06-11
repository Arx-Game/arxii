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

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.checks.models import Consequence


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
    except Exception:  # noqa: BLE001 - theater must never break resolution
        return False
    return True
