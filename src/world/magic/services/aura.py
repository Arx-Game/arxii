"""Aura / affinity-percentage service functions for the magic system."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from world.magic.models import AuraAffinityThreshold, CharacterAura, CharacterResonance
from world.magic.types import AffinityType, AuraDrift, AuraPercentages

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


def recompute_aura(character_sheet: CharacterSheet) -> AuraDrift | None:
    """Recompute CharacterAura's stored percentages from resonance-earning history.

    Sums CharacterResonance.lifetime_earned grouped by Resonance.affinity and
    normalizes to percentages, writing through to the stored CharacterAura row
    (the mechanism every live read call site — power_terms, resonance_environment,
    soul_tether — actually consumes).

    Called from grant_resonance() on every grant system-wide, so aura reflects
    the character's whole earning history, not just one source.

    Returns None (no-op) if the character has no CharacterAura row (not
    magically active). Returns None-equivalent-but-actually-an-AuraDrift with
    before==after if total lifetime_earned is 0 (leaves stored values as-is —
    no divide-by-zero flip to an even split).
    """
    try:
        aura = CharacterAura.objects.get(character=character_sheet.character)
    except CharacterAura.DoesNotExist:
        return None

    before = AuraPercentages(
        celestial=float(aura.celestial),
        primal=float(aura.primal),
        abyssal=float(aura.abyssal),
    )

    totals: dict[str, int] = {"celestial": 0, "primal": 0, "abyssal": 0}
    rows = CharacterResonance.objects.filter(character_sheet=character_sheet).select_related(
        "resonance__affinity"
    )
    for row in rows:
        affinity_name = row.resonance.affinity.name.lower()
        if affinity_name in totals:
            totals[affinity_name] += row.lifetime_earned

    grand_total = sum(totals.values())
    if grand_total == 0:
        return AuraDrift(before=before, after=before)

    aura.celestial = Decimal(totals["celestial"]) / Decimal(grand_total) * 100
    aura.primal = Decimal(totals["primal"]) / Decimal(grand_total) * 100
    aura.abyssal = Decimal(totals["abyssal"]) / Decimal(grand_total) * 100
    # Correct rounding drift so the three fields sum to exactly 100.00 (the
    # model's clean() enforces this invariant on save()).
    aura.celestial = aura.celestial.quantize(Decimal("0.01"))
    aura.primal = aura.primal.quantize(Decimal("0.01"))
    # celestial and primal are each individually always in [0, 100] by
    # construction (each is a non-negative ratio of a non-negative total to a
    # positive grand_total, times 100), so their sum is always in [0, 200].
    # abyssal's TRUE (pre-rounding) value is always >= 0, since it equals
    # 100 - true_celestial_pct - true_primal_pct and the three true percentages
    # sum to exactly 100 by definition (they partition the same grand_total).
    # Independent 2-decimal quantization of celestial/primal introduces at most
    # ~0.01 combined rounding error, so the derived abyssal below is only
    # theoretically at risk of drifting fractionally outside [0, 100] — and
    # only for adversarial arbitrary-decimal inputs. This function's real input
    # domain is CharacterResonance.lifetime_earned, a PositiveIntegerField
    # (always non-negative integers), and an exhaustive brute-force sweep of
    # ~4.2M integer (celestial_total, primal_total, abyssal_total) splits
    # through this exact Decimal/quantize arithmetic found ZERO cases where the
    # derived abyssal left [0, 100] (see
    # test_recompute_never_violates_bounds_across_integer_split_range). A
    # clamp here was tried and reverted (#1737): clamping abyssal alone without
    # compensating celestial/primal breaks the sum==100.00 invariant that
    # CharacterAura.clean() enforces, trading one ValidationError for another.
    # No runtime guard is warranted for a case unreachable from real inputs.
    aura.abyssal = Decimal("100.00") - aura.celestial - aura.primal
    aura.save()

    after = AuraPercentages(
        celestial=float(aura.celestial),
        primal=float(aura.primal),
        abyssal=float(aura.abyssal),
    )
    return AuraDrift(before=before, after=after)


def _achievement_gate_passes(achievement, character_sheet: CharacterSheet) -> bool:
    """True if every AchievementRequirement on `achievement` is met by `character_sheet`.

    No requirements at all => passes (this mirrors an authored achievement with
    zero stat gates, i.e. the crossing itself is the only condition).
    """
    from world.achievements.models import AchievementRequirement  # noqa: PLC0415
    from world.achievements.services import get_stat  # noqa: PLC0415

    reqs = list(AchievementRequirement.objects.filter(achievement=achievement))
    return all(req.is_met(get_stat(character_sheet, req.stat)) for req in reqs)


def fire_aura_threshold_crossings(character_sheet: CharacterSheet, drift: AuraDrift) -> None:
    """Grant achievements for any AuraAffinityThreshold crossed by this drift.

    For each affinity, checks whether `drift.after`'s percentage for that
    affinity crossed any authored threshold_percent in (before, after].
    Idempotent (skips already-earned achievements, mirroring
    world.covenants.discovery._fire_one). Compound gates (an achievement's own
    AchievementRequirement rows) are checked via the character's own stat
    values before granting.

    Called explicitly by grant_resonance() (the AuraDrift returned by
    recompute_aura() is passed straight through), or by test code directly with
    a constructed/returned AuraDrift.
    """
    from world.achievements.models import CharacterAchievement  # noqa: PLC0415
    from world.achievements.services import grant_achievement  # noqa: PLC0415

    per_affinity_after = {
        AffinityType.CELESTIAL: drift.after.celestial,
        AffinityType.PRIMAL: drift.after.primal,
        AffinityType.ABYSSAL: drift.after.abyssal,
    }
    per_affinity_before = {
        AffinityType.CELESTIAL: drift.before.celestial,
        AffinityType.PRIMAL: drift.before.primal,
        AffinityType.ABYSSAL: drift.before.abyssal,
    }

    for affinity, after_value in per_affinity_after.items():
        before_value = per_affinity_before[affinity]
        if after_value <= before_value:
            continue
        thresholds = AuraAffinityThreshold.objects.filter(
            affinity=affinity,
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
