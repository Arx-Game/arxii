"""Touchstone combat resonance service (#2023).

An attuned touchstone (ItemInstance whose template.tied_resonance is set)
empowers casts of its tied resonance. The bonus is modest and tier-scaled,
flowing through the power-term provider seam in _derive_power.
"""

from __future__ import annotations

from world.magic.models import TouchstoneCastConfig


def get_touchstone_cast_config() -> TouchstoneCastConfig:
    """Lazy-create and return the singleton TouchstoneCastConfig (pk=1)."""
    obj, _created = TouchstoneCastConfig.objects.get_or_create(pk=1)
    return obj


def touchstone_cast_bonus(sheet: object, resonance: object) -> int:
    """Sum the touchstone cast bonus for a resonance across equipped items.

    Scans the character's equipped items for any ItemInstance whose
    ``template.tied_resonance`` matches the given resonance. The bonus is
    ``resonance_tier.tier_level * config_scale / 10`` per matching touchstone.

    Args:
        sheet: CharacterSheet instance.
        resonance: Resonance instance to match against.

    Returns:
        Integer total (0 when no matching touchstone is equipped).
    """
    char = sheet.character
    if not hasattr(char, "equipped_items"):
        return 0
    config = get_touchstone_cast_config()
    total = 0
    for equipped in char.equipped_items:
        inst = equipped.item_instance
        template = inst.template
        if template.tied_resonance_id is None or template.resonance_tier_id is None:
            continue
        if template.tied_resonance_id != resonance.pk:
            continue
        total += template.resonance_tier.tier_level * config.config_scale // 10
    return total
