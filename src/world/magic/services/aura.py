"""Aura / affinity-percentage service functions for the magic system."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from world.magic.models import CharacterAura, CharacterResonance
from world.magic.types import AffinityType, AuraDrift, AuraPercentages
from world.mechanics.constants import RESONANCE_CATEGORY_NAME

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Resonance as ResonanceModel


def calculate_affinity_breakdown(resonances: QuerySet[ResonanceModel]) -> dict[str, int]:
    """Derive affinity counts from a set of resonances.

    Args:
        resonances: QuerySet of Resonance instances.

    Returns:
        Dict mapping affinity name to count of resonances with that affinity.
    """
    counts: dict[str, int] = {}
    for resonance in resonances.select_related("affinity").all():
        aff_name = resonance.affinity.name
        counts[aff_name] = counts.get(aff_name, 0) + 1
    return counts


def get_aura_percentages(character_sheet: CharacterSheet) -> AuraPercentages:
    """
    Calculate aura percentages from affinity totals and resonance-targeting modifiers.

    The aura represents a character's soul-state across the three magical
    affinities (Celestial, Primal, Abyssal). Percentages are calculated from:
    1. Direct affinity totals (CharacterAffinityTotal).
    2. Per-resonance contributions, derived live from CharacterModifier rows whose
       target points at a Resonance (via ModifierTarget.target_resonance) in the
       resonance category. Each modifier's value contributes to its resonance's
       affinity bucket.

    The legacy CharacterResonanceTotal denormalization has been removed; the
    CharacterModifier rows are the single source of truth for resonance-driven
    aura contributions.

    Args:
        character_sheet: A CharacterSheet instance with related affinity_totals.
                         Resonance contributions are read from CharacterModifier
                         rows on this sheet.

    Returns:
        AuraPercentages dataclass with celestial, primal, abyssal percentages
        (floats summing to 100). If no totals exist, returns an even split.
    """
    from world.mechanics.models import CharacterModifier  # noqa: PLC0415

    affinity_totals: dict[str, int] = {
        AffinityType.CELESTIAL: 0,
        AffinityType.PRIMAL: 0,
        AffinityType.ABYSSAL: 0,
    }

    # Direct affinity totals (CharacterAffinityTotal — kept).
    for at in character_sheet.affinity_totals.select_related("affinity"):
        aff_name = at.affinity.name.lower()
        if aff_name in affinity_totals:
            affinity_totals[aff_name] = at.total

    # Resonance contributions — sum CharacterModifier values whose target points
    # at a Resonance in the resonance category, grouped by the resonance's affinity.
    resonance_modifiers = CharacterModifier.objects.filter(
        character=character_sheet,
        target__category__name=RESONANCE_CATEGORY_NAME,
        target__target_resonance__isnull=False,
    ).select_related("target__target_resonance__affinity")

    for mod in resonance_modifiers:
        affinity_name = mod.target.target_resonance.affinity.name.lower()
        if affinity_name in affinity_totals:
            affinity_totals[affinity_name] += mod.value

    grand_total = sum(affinity_totals.values())
    if grand_total == 0:
        return AuraPercentages(celestial=33.33, primal=33.33, abyssal=33.34)

    return AuraPercentages(
        celestial=(affinity_totals[AffinityType.CELESTIAL] / grand_total) * 100,
        primal=(affinity_totals[AffinityType.PRIMAL] / grand_total) * 100,
        abyssal=(affinity_totals[AffinityType.ABYSSAL] / grand_total) * 100,
    )


def recompute_aura(character_sheet: CharacterSheet) -> AuraDrift | None:
    """Recompute CharacterAura's stored percentages from resonance-earning history.

    Sums CharacterResonance.lifetime_earned grouped by Resonance.affinity and
    normalizes to percentages, writing through to the stored CharacterAura row
    (the mechanism every live read call site — power_terms, resonance_environment,
    soul_tether — actually consumes; see #1739 for the unrelated, unwired
    get_aura_percentages()/CharacterAffinityTotal legacy pair above, which this
    function does not touch).

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
    aura.abyssal = Decimal("100.00") - aura.celestial - aura.primal
    # Clamp against the (essentially-adversarial) edge case where celestial's and
    # primal's independent rounding errors combine to push the derived abyssal
    # fractionally outside [0, 100] — CharacterAura's validators would otherwise
    # raise ValidationError in full_clean() on save().
    aura.abyssal = max(Decimal("0.00"), min(Decimal("100.00"), aura.abyssal))
    aura.save()

    after = AuraPercentages(
        celestial=float(aura.celestial),
        primal=float(aura.primal),
        abyssal=float(aura.abyssal),
    )
    return AuraDrift(before=before, after=after)
