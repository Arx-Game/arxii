"""Distinction -> Resonance consumer services (#1834).

Reads the ``DistinctionResonanceGrant`` authoring sidecar (``world.magic.models.grants``)
to derive per-character currency effects on read — no denormalized totals, no cached
columns. ``distinction_earn_rate_for`` backs the earn-rate accelerator wired into
``grant_resonance`` (``services/resonance.py``); ``reconcile_distinction_resonance_grants``
(Task 4) will add the flat-seed reconciliation pass to this same module.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Resonance as ResonanceModel


def distinction_earn_rate_for(
    character_sheet: CharacterSheet,
    resonance: ResonanceModel,
) -> Decimal:
    """Sum the earn-rate bonus (percent) a character's distinctions grant for ``resonance``.

    One query (join across ``CharacterDistinction -> Distinction ->
    DistinctionResonanceGrant``), scaled by the character's rank in each matching
    distinction. Callers that loop over many characters (e.g. a daily trickle tick)
    must call this once per character — this function itself never loops a query.

    Args:
        character_sheet: The character whose distinctions are being summed.
        resonance: The Resonance being earned.

    Returns:
        The summed percent bonus (0 when no distinction grants a bonus for this
        resonance).
    """
    from world.distinctions.models import CharacterDistinction  # noqa: PLC0415

    rows = CharacterDistinction.objects.filter(
        character_id=character_sheet.pk,
        distinction__resonance_grants__resonance=resonance,
    ).values_list("rank", "distinction__resonance_grants__earn_rate_bonus_per_rank")

    return sum(
        (Decimal(rank) * bonus for rank, bonus in rows),
        Decimal(0),
    )
