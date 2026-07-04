"""Distinction -> Resonance consumer services (#1834).

Reads the ``DistinctionResonanceGrant`` authoring sidecar (``world.magic.models.grants``)
to derive per-character currency effects on read — no denormalized totals, no cached
columns. ``distinction_earn_rate_for`` backs the earn-rate accelerator wired into
``grant_resonance`` (``services/resonance.py``); ``reconcile_distinction_resonance_grants``
is the grant-time consumer — called whenever a character gains/ranks-up a distinction —
that establishes the character's resonance and tops off a rank-scaled, ledger-idempotent
flat seed.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import models, transaction

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.distinctions.models import CharacterDistinction
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


@transaction.atomic
def reconcile_distinction_resonance_grants(character_distinction: CharacterDistinction) -> None:
    """Reconcile a ``CharacterDistinction`` into the character's resonance standing.

    Called at grant time whenever a character gains a distinction or ranks it up. For
    every ``DistinctionResonanceGrant`` authored on ``character_distinction.distinction``:

    1. **Establish** — ``get_or_create`` a ``CharacterResonance`` row for the grant's
       resonance (balance/lifetime_earned default to 0), so the character is claimed
       into that resonance even before any seed amount is owed.
    2. **Seed top-off** — the rank-scaled flat target is
       ``grant.flat_amount_per_rank * character_distinction.rank``. Ledger-idempotent:
       sums this distinction's prior DISTINCTION grants for this resonance and only
       grants the shortfall (``target - already``, floored at 0). A second reconcile
       with no rank change grants 0 (no new ledger row); a rank-down never debits —
       ``CharacterResonance.lifetime_earned`` is monotonic and clawback is impossible.

    Args:
        character_distinction: The CharacterDistinction being reconciled.
    """
    from world.magic.constants import GainSource  # noqa: PLC0415
    from world.magic.models import CharacterResonance, ResonanceGrant  # noqa: PLC0415
    from world.magic.models.grants import DistinctionResonanceGrant  # noqa: PLC0415
    from world.magic.services.resonance import grant_resonance  # noqa: PLC0415

    sheet = character_distinction.character.sheet_data

    grants = DistinctionResonanceGrant.objects.filter(distinction=character_distinction.distinction)
    for grant in grants:
        CharacterResonance.objects.get_or_create(
            character_sheet=sheet,
            resonance=grant.resonance,
            defaults={"balance": 0, "lifetime_earned": 0},
        )

        target = grant.flat_amount_per_rank * character_distinction.rank
        already = (
            ResonanceGrant.objects.filter(
                source=GainSource.DISTINCTION,
                source_character_distinction=character_distinction,
                resonance=grant.resonance,
            ).aggregate(models.Sum("amount"))["amount__sum"]
            or 0
        )
        delta = max(0, target - already)
        if delta > 0:
            grant_resonance(
                sheet,
                grant.resonance,
                delta,
                source=GainSource.DISTINCTION,
                source_character_distinction=character_distinction,
            )
