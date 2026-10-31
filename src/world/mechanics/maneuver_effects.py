"""The maneuver effect catalog's code side (#4783).

``ensure_maneuver_effects`` writes the eight fixed rows (and the modifier category their
targets live in) from explicit values; ``get_maneuver_effect`` is how code finds one row,
always by key and never by name.
"""

from world.mechanics.constants import (
    MANEUVER_EFFECT_CATEGORY_NAME,
    MANEUVER_EFFECT_DEFAULTS,
    ManeuverEffectKey,
)
from world.mechanics.models import ManeuverEffect, ModifierCategory

_CATEGORY_DESCRIPTION = (
    "Targets for the numbers a combat maneuver has (Charge damage, Cover escape bonus, "
    "partial protection and so on). Scope each target to one effect or one kind of effect."
)


def ensure_maneuver_effects() -> list[ManeuverEffect]:
    """Get-or-create every catalog row with today's value, and the target category.

    Idempotent. An edited base value is kept: only a missing row is written.
    """
    ModifierCategory.objects.get_or_create(
        name=MANEUVER_EFFECT_CATEGORY_NAME,
        defaults={"description": _CATEGORY_DESCRIPTION},
    )
    return [get_maneuver_effect(key) for key in ManeuverEffectKey]


def get_maneuver_effect(key: str) -> ManeuverEffect:
    """The catalog row for ``key``, written with its default if it is missing."""
    effect, _ = ManeuverEffect.objects.get_or_create(
        key=key, defaults={"base_value": MANEUVER_EFFECT_DEFAULTS[key]}
    )
    return effect
