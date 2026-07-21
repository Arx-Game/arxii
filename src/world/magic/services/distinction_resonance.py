"""Distinction -> Resonance consumer services (#1834).

Reads the ``DistinctionResonanceGrant`` authoring sidecar (``world.magic.models.grants``)
to derive per-character currency effects on read — no denormalized totals, no cached
columns. ``distinction_earn_rate_for`` backs the earn-rate accelerator wired into
``grant_resonance`` (``services/resonance.py``); ``reconcile_distinction_resonance_grants``
is the grant-time consumer — intended to be called whenever a character gains/ranks-up a
distinction (wired into those paths by Task 5/6) — that establishes the character's
resonance and tops off a rank-scaled, ledger-idempotent flat seed.

``check_distinction_rank_thresholds`` (#2037 Decision 8) is the reverse direction: reads
the ``DistinctionResonanceRankThreshold`` sidecar to rank up a Distinction the character
already holds once sustained investment in a Resonance crosses an authored threshold.
"""

from __future__ import annotations

from decimal import Decimal
import logging
from typing import TYPE_CHECKING

from django.db import models, transaction

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.distinctions.models import CharacterDistinction
    from world.magic.models import Resonance as ResonanceModel

logger = logging.getLogger(__name__)


def distinction_earn_rate_for(
    character_sheet: CharacterSheet,
    resonance: ResonanceModel,
) -> Decimal:
    """Sum the earn-rate bonus (percent) a character's distinctions grant for ``resonance``.

    One query (join across ``CharacterDistinction -> Distinction ->
    DistinctionResonanceGrant``), scaled by the character's rank in each matching
    distinction. The live caller (``grant_resonance``) invokes this once per grant
    call — e.g. once per equipped item facet, not once per character — so this
    function must never loop a query internally; each call is a single query.

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

    Intended to be called at grant time whenever a character gains a distinction or
    ranks it up (wired into the distinction-grant/rank-change paths by Task 5/6 — not
    yet wired as of this function's introduction). For every ``DistinctionResonanceGrant``
    authored on ``character_distinction.distinction``:

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

    sheet = character_distinction.character

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


def check_distinction_rank_thresholds(
    character_sheet: CharacterSheet,
    resonance: ResonanceModel,
) -> None:
    """Rank up held Distinctions whose ``DistinctionResonanceRankThreshold`` was crossed.

    Called from ``grant_resonance`` (#2037 Decision 8) only when ``source`` is one of
    ``ACCELERATED_GAIN_SOURCES`` — the "sustained endorsements around a resonance"
    identity-reinforcing-play cluster. Never fires for a ``DISTINCTION``-source grant
    (that source is never in ``ACCELERATED_GAIN_SOURCES``), which is what prevents a
    feedback loop: a distinction's own resonance seed (``reconcile_distinction_resonance_
    grants``) could otherwise immediately rank the same distinction back up.

    RANKS UP HELD DISTINCTIONS ONLY — this never grants a distinction the character
    doesn't already hold; only ``CharacterDistinction`` rows for ``distinction`` at
    exactly ``current_rank + 1`` are candidates. This is the guard against the
    endorsement-threshold path minting a Distinction fresh, and it's also what makes the
    re-fire guard work: once a threshold at ``rank`` fires, the character's rank moves to
    (at least) ``rank``, so ``current_rank + 1`` no longer matches that row — a repeat
    grant past the same threshold is a no-op.

    **Cheap when no thresholds are authored** — the whole check is one query (a join from
    the sheet's held ``CharacterDistinction`` rows through ``Distinction`` to
    ``DistinctionResonanceRankThreshold``, filtered on this resonance, the exact
    ``rank + 1`` match, and the lifetime-earned comparison, all in the WHERE clause); an
    empty result returns immediately. No per-distinction query loop.

    **Multi-level catch-up** (#2037 Task 3 review flag): a sheet that crosses two
    thresholds' worth of ``lifetime_earned`` in one grant call is looped to a fully
    caught-up state, not advanced by one rank per call — re-running the single-query
    candidate check after every successful rank-up until nothing more qualifies. This is
    the deterministic-final-state choice the plan recommended; the alternative (advance
    one rank per ``grant_resonance`` call, requiring N further grants to fully catch up)
    was rejected as a source of confusing "why hasn't it ranked up yet" staleness for a
    quantity (lifetime-earned resonance) that only ever grows.

    Args:
        character_sheet: The character whose held distinctions may rank up.
        resonance: The Resonance whose lifetime-earned total just changed.
    """
    from world.distinctions.exceptions import DistinctionExclusionError  # noqa: PLC0415
    from world.distinctions.models import CharacterDistinction  # noqa: PLC0415
    from world.distinctions.services import grant_distinction  # noqa: PLC0415
    from world.distinctions.types import DistinctionOrigin  # noqa: PLC0415
    from world.magic.models import CharacterResonance  # noqa: PLC0415

    while True:
        lifetime_earned = (
            CharacterResonance.objects.filter(character_sheet=character_sheet, resonance=resonance)
            .values_list("lifetime_earned", flat=True)
            .first()
        )
        if not lifetime_earned:
            return

        candidates = list(
            CharacterDistinction.objects.filter(
                character=character_sheet,
                distinction__resonance_rank_thresholds__resonance=resonance,
                distinction__resonance_rank_thresholds__rank=models.F("rank") + 1,
                distinction__resonance_rank_thresholds__lifetime_earned_threshold__lte=(
                    lifetime_earned
                ),
            )
            .select_related("distinction")
            .annotate(
                threshold_rank=models.F("distinction__resonance_rank_thresholds__rank"),
            )
        )
        if not candidates:
            return

        progressed = False
        for character_distinction in candidates:
            try:
                grant_distinction(
                    character_sheet,
                    character_distinction.distinction,
                    rank=character_distinction.threshold_rank,
                    origin=DistinctionOrigin.ENDORSEMENT_THRESHOLD,
                )
                progressed = True
            except DistinctionExclusionError:
                logger.warning(
                    "Endorsement-threshold rank-up of distinction #%s to rank %s "
                    "blocked by exclusion conflict on character sheet #%s — skipping.",
                    character_distinction.distinction_id,
                    character_distinction.threshold_rank,
                    character_sheet.pk,
                )
        if not progressed:
            return
