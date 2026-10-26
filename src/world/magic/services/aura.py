"""Aura / affinity-percentage service functions for the magic system."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import transaction

from world.magic.models import (
    Affinity,
    AuraAffinityThreshold,
    CharacterAura,
    CharacterAuraShare,
    CharacterResonance,
)
from world.magic.types import AffinityShare, AuraDrift, AuraPercentages

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Resonance

_CENT = Decimal("0.01")
_FULL = Decimal("100.00")
#: Starting aura: the picked resonance's affinity holds the larger share (ruled, #4681).
_STARTING_MAJOR = Decimal("80.00")
_STARTING_MINOR = Decimal("20.00")


def aura_percentages(aura: CharacterAura) -> AuraPercentages:
    """Snapshot of an aura's stored shares, ordered by affinity pk."""
    shares = sorted(aura.cached_shares, key=lambda share: share.affinity_id)
    return AuraPercentages(
        shares=tuple(AffinityShare(affinity=s.affinity, percent=s.percent) for s in shares)
    )


@transaction.atomic
def set_aura_shares(aura: CharacterAura, shares: Sequence[AffinityShare]) -> None:
    """Replace an aura's share rows. The only writer of CharacterAuraShare.

    Upserts a row per share, deletes rows for affinities not given, rounds each
    percent to 0.01 and folds any rounding remainder into the largest share (ties:
    lowest affinity pk) so the shares sum to exactly 100.00. Clears the aura's share
    cache.

    Raises ValueError if the shares are empty, repeat an affinity, or are not within
    rounding of 100.
    """
    if not shares:
        msg = "An aura needs at least one affinity share."
        raise ValueError(msg)
    rounded = {}
    for share in shares:
        if share.affinity.pk in rounded:
            msg = "An aura holds one share per affinity."
            raise ValueError(msg)
        rounded[share.affinity.pk] = (share.affinity, share.percent.quantize(_CENT))
    remainder = _FULL - sum((pct for _, pct in rounded.values()), Decimal(0))
    if abs(remainder) > _CENT * len(rounded):
        msg = f"Aura shares must sum to 100, got {_FULL - remainder}."
        raise ValueError(msg)
    if remainder:
        largest_pk = min(rounded, key=lambda pk: (-rounded[pk][1], pk))
        affinity, pct = rounded[largest_pk]
        rounded[largest_pk] = (affinity, pct + remainder)

    aura.shares.exclude(affinity_id__in=list(rounded)).delete()
    existing = {row.affinity_id: row for row in aura.shares.all()}
    for pk, (affinity, pct) in rounded.items():
        row = existing.get(pk)
        if row is None:
            CharacterAuraShare.objects.create(aura=aura, affinity=affinity, percent=pct)
        elif row.percent != pct:
            row.percent = pct
            row.save()
    aura.__dict__.pop("cached_shares", None)


def starting_aura_shares(resonance: Resonance | None) -> list[AffinityShare]:
    """The aura a character begins with, before any resonance has been earned.

    The picked resonance's affinity holds 80.00 and Abyssal 20.00 (Primal 20.00 when the
    pick is itself Abyssal). With no pick: Primal 80.00, Abyssal 20.00.
    """
    abyssal = Affinity.objects.get_abyssal_affinity()
    if resonance is None:
        major = Affinity.objects.get_primal_affinity()
    else:
        major = resonance.affinity
    minor = Affinity.objects.get_primal_affinity() if major.pk == abyssal.pk else abyssal
    return [
        AffinityShare(affinity=major, percent=_STARTING_MAJOR),
        AffinityShare(affinity=minor, percent=_STARTING_MINOR),
    ]


def recompute_aura(character_sheet: CharacterSheet) -> AuraDrift | None:
    """Recompute the aura's shares from resonance-earning history.

    Sums CharacterResonance.lifetime_earned grouped by Resonance.affinity (every
    affinity the character has earned in, however many) and normalizes to percentages,
    writing through to the CharacterAuraShare rows.

    Called from grant_resonance() on every grant system-wide, so aura reflects
    the character's whole earning history, not just one source.

    Returns None (no-op) if the character has no CharacterAura row (not
    magically active). If total lifetime_earned is 0 the stored shares are left as-is
    and the drift has before == after (no divide-by-zero flip to an even split).
    """
    try:
        aura = CharacterAura.objects.get(character=character_sheet)
    except CharacterAura.DoesNotExist:
        return None

    before = aura_percentages(aura)

    totals: dict[int, int] = defaultdict(int)
    affinities: dict[int, Affinity] = {}
    rows = CharacterResonance.objects.filter(character_sheet=character_sheet).select_related(
        "resonance__affinity"
    )
    for row in rows:
        affinity = row.resonance.affinity
        affinities[affinity.pk] = affinity
        totals[affinity.pk] += row.lifetime_earned

    grand_total = sum(totals.values())
    if grand_total == 0:
        return AuraDrift(before=before, after=before)

    set_aura_shares(
        aura,
        [
            AffinityShare(
                affinity=affinities[pk], percent=Decimal(total) / Decimal(grand_total) * 100
            )
            for pk, total in sorted(totals.items())
            if total
        ],
    )
    return AuraDrift(before=before, after=aura_percentages(aura))


def _achievement_gate_passes(achievement, character_sheet: CharacterSheet) -> bool:
    """True if every AchievementStatRequirement on `achievement` is met by `character_sheet`.

    No requirements at all => passes (this mirrors an authored achievement with
    zero stat gates, i.e. the crossing itself is the only condition).
    """
    from world.achievements.models import AchievementStatRequirement  # noqa: PLC0415
    from world.achievements.services import get_stat  # noqa: PLC0415

    reqs = list(AchievementStatRequirement.objects.filter(achievement=achievement))
    return all(req.is_met(get_stat(character_sheet, req.stat)) for req in reqs)


def fire_aura_threshold_crossings(character_sheet: CharacterSheet, drift: AuraDrift) -> None:
    """Grant achievements for any AuraAffinityThreshold crossed by this drift.

    For each affinity, checks whether `drift.after`'s percentage for that
    affinity crossed any authored threshold_percent in (before, after].
    Idempotent (skips already-earned achievements, mirroring
    world.covenants.discovery._fire_one). Compound gates (an achievement's own
    AchievementStatRequirement rows) are checked via the character's own stat
    values before granting.

    Called explicitly by grant_resonance() (the AuraDrift returned by
    recompute_aura() is passed straight through), or by test code directly with
    a constructed/returned AuraDrift.
    """
    from world.achievements.models import CharacterAchievement  # noqa: PLC0415
    from world.achievements.services import grant_achievement  # noqa: PLC0415

    for share in drift.after.shares:
        after_value = share.percent
        before_value = drift.before.percent_for(share.affinity)
        if after_value <= before_value:
            continue
        thresholds = AuraAffinityThreshold.objects.filter(
            affinity_ref=share.affinity,
            threshold_percent__gt=before_value,
            threshold_percent__lte=after_value,
            discovery_achievement__isnull=False,
        ).select_related("discovery_achievement")
        for threshold in thresholds:
            achievement = threshold.discovery_achievement
            if CharacterAchievement.objects.filter(
                character_sheet=character_sheet, achievement=achievement
            ).exists():
                continue
            if not _achievement_gate_passes(achievement, character_sheet):
                continue
            grant_achievement(achievement, [character_sheet])
