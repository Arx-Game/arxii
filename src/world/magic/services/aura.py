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

_CENT = Decimal("0.01")
_FULL = Decimal("100.00")


def ensure_aura(character_sheet: CharacterSheet) -> CharacterAura:
    """The sheet's aura, creating an empty one (no shares) when it has none.

    Only character creation writes an aura, so a character minted another way (a story
    NPC a GM runs) has none. An empty aura holds no affinity shares, which no gate reads
    as a primary affinity, and it gains shares through the first resonance grant.
    """
    aura = character_sheet.aura_or_none
    if aura is not None:
        return aura
    aura, _ = CharacterAura.objects.get_or_create(character=character_sheet)
    return aura


def aura_percentages(aura: CharacterAura) -> AuraPercentages:
    """Snapshot of an aura's stored shares, ordered by affinity pk."""
    shares = sorted(aura.cached_shares, key=lambda share: share.affinity_id)
    return AuraPercentages(
        shares=tuple(AffinityShare(affinity=s.affinity, percent=s.percent) for s in shares)
    )


def _retire_absent_shares(aura: CharacterAura, kept_affinity_ids: list[int]) -> None:
    """Drop share rows for affinities not kept; one holding a settled share stays at 0.00."""
    absent = aura.shares.exclude(affinity_id__in=kept_affinity_ids)
    absent.filter(settled_percent=0).delete()
    for row in absent.filter(settled_percent__gt=0, percent__gt=0):
        row.percent = Decimal(0)
        row.save()


def _normalized_shares(
    shares: Sequence[AffinityShare], *, subject: str, label: str
) -> dict[int, tuple[Affinity, Decimal]]:
    """Each share rounded to 0.01, with the rounding remainder folded into the largest.

    The largest share ties to the lowest affinity pk, and the result sums to exactly 100.00.
    Raises ValueError (worded with ``subject`` and ``label``) if the shares are empty,
    repeat an affinity, or are not within rounding of 100.
    """
    if not shares:
        msg = f"{subject} needs at least one affinity share."
        raise ValueError(msg)
    rounded: dict[int, tuple[Affinity, Decimal]] = {}
    for share in shares:
        if share.affinity.pk in rounded:
            msg = f"{subject} holds one share per affinity."
            raise ValueError(msg)
        rounded[share.affinity.pk] = (share.affinity, share.percent.quantize(_CENT))
    remainder = _FULL - sum((pct for _, pct in rounded.values()), Decimal(0))
    if abs(remainder) > _CENT * len(rounded):
        msg = f"{label} must sum to 100, got {_FULL - remainder}."
        raise ValueError(msg)
    if remainder:
        largest_pk = min(rounded, key=lambda pk: (-rounded[pk][1], pk))
        affinity, pct = rounded[largest_pk]
        rounded[largest_pk] = (affinity, pct + remainder)
    return rounded


@transaction.atomic
def set_aura_shares(aura: CharacterAura, shares: Sequence[AffinityShare]) -> None:
    """Replace an aura's share rows. The only writer of CharacterAuraShare.

    Upserts a row per share, rounds each percent to 0.01 and folds any rounding
    remainder into the largest share (ties: lowest affinity pk) so the shares sum to
    exactly 100.00. A row for an affinity not given is deleted, unless it still holds a
    settled share: that row stays at 0.00 so a faded streak's line survives and the
    streak can return up to it without unsettling the character (#5123). Clears the
    aura's share cache.

    Raises ValueError if the shares are empty, repeat an affinity, or are not within
    rounding of 100.
    """
    rounded = _normalized_shares(shares, subject="An aura", label="Aura shares")

    _retire_absent_shares(aura, list(rounded))
    existing = {row.affinity_id: row for row in aura.shares.all()}
    for pk, (affinity, pct) in rounded.items():
        row = existing.get(pk)
        if row is None:
            CharacterAuraShare.objects.create(aura=aura, affinity=affinity, percent=pct)
        elif row.percent != pct:
            row.percent = pct
            row.save()
    aura.__dict__.pop("cached_shares", None)


@transaction.atomic
def set_settled_shares(aura: CharacterAura, shares: Sequence[AffinityShare]) -> None:
    """Write who the character is, per affinity, without touching the aura they have.

    Rounds each percent to 0.01 and folds any remainder into the largest share (ties:
    lowest affinity pk) so the settled shares sum to 100.00. An affinity not given is
    settled at 0; an affinity given with no share row yet gets one at 0.00 (the character
    is settled in an affinity they have no resonance in, yet). A row left holding neither
    a share nor a settled share is deleted.

    Raises ValueError if the shares are empty, repeat an affinity, or are not within
    rounding of 100.
    """
    rounded = _normalized_shares(shares, subject="A settled self", label="Settled shares")

    existing = {row.affinity_id: row for row in aura.shares.all()}
    for pk, row in existing.items():
        if pk in rounded:
            continue
        if row.percent == 0:
            row.delete()
        elif row.settled_percent != 0:
            row.settled_percent = Decimal(0)
            row.save(update_fields=["settled_percent"])
    for pk, (affinity, pct) in rounded.items():
        row = existing.get(pk)
        if row is None:
            CharacterAuraShare.objects.create(
                aura=aura, affinity=affinity, percent=Decimal(0), settled_percent=pct
            )
        elif row.settled_percent != pct:
            row.settled_percent = pct
            row.save(update_fields=["settled_percent"])
    aura.__dict__.pop("cached_shares", None)


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
            affinity=share.affinity,
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
