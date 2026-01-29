"""
Magic system service functions.

This module provides service functions for the magic system, including
calculations for aura percentages based on affinity and resonance totals.
"""

from django.db.models import F

from world.magic.models import CharacterResonanceTotal
from world.magic.types import AffinityType


def add_resonance_total(character_sheet, resonance, amount: int) -> None:
    """
    Add to a character's resonance total.

    Creates the CharacterResonanceTotal if it doesn't exist.

    Args:
        character_sheet: CharacterSheet instance
        resonance: ModifierType instance (must be category='resonance')
        amount: Amount to add (can be negative)
    """
    total, created = CharacterResonanceTotal.objects.get_or_create(
        character=character_sheet,
        resonance=resonance,
        defaults={"total": amount},
    )
    if not created:
        # Update using F() to avoid race conditions
        CharacterResonanceTotal.objects.filter(pk=total.pk).update(total=F("total") + amount)
        # Flush from SharedMemoryModel cache since we bypassed the model layer
        total.flush_from_cache(force=True)


def get_aura_percentages(character_sheet) -> dict[str, float]:
    """
    Calculate aura percentages from affinity and resonance totals.

    The aura represents a character's soul-state across the three magical
    affinities (Celestial, Primal, Abyssal). Percentages are calculated from:
    1. Direct affinity totals (CharacterAffinityTotal)
    2. Resonance contributions (CharacterResonanceTotal via affiliated_affinity)

    Args:
        character_sheet: A CharacterSheet instance with related affinity_totals
                        and resonance_totals.

    Returns:
        dict with celestial, primal, abyssal percentages (floats summing to 100).
        If no totals exist, returns an even split (33.33/33.33/33.34).
    """
    # Initialize affinity totals
    affinity_totals = {
        AffinityType.CELESTIAL: 0,
        AffinityType.PRIMAL: 0,
        AffinityType.ABYSSAL: 0,
    }

    # Get direct affinity totals
    for at in character_sheet.affinity_totals.all():
        affinity_totals[at.affinity_type] = at.total

    # Add resonance contributions via affiliated_affinity
    for rt in character_sheet.resonance_totals.select_related("resonance__affiliated_affinity"):
        if rt.resonance.affiliated_affinity:
            # The affiliated_affinity is a ModifierType with category='affinity'
            # Its name should be 'Celestial', 'Primal', or 'Abyssal' (title case)
            affinity_name = rt.resonance.affiliated_affinity.name.lower()
            if affinity_name in [
                AffinityType.CELESTIAL,
                AffinityType.PRIMAL,
                AffinityType.ABYSSAL,
            ]:
                affinity_totals[affinity_name] += rt.total

    # Calculate percentages
    grand_total = sum(affinity_totals.values())
    if grand_total == 0:
        return {"celestial": 33.33, "primal": 33.33, "abyssal": 33.34}

    return {
        "celestial": (affinity_totals[AffinityType.CELESTIAL] / grand_total) * 100,
        "primal": (affinity_totals[AffinityType.PRIMAL] / grand_total) * 100,
        "abyssal": (affinity_totals[AffinityType.ABYSSAL] / grand_total) * 100,
    }
