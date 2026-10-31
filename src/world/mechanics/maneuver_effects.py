"""The maneuver effect catalog's code side (#4783).

``ensure_maneuver_effect_rows`` writes the eight fixed rows from explicit values; the
combat seed cluster calls it. ``ensure_maneuver_effects`` writes the rows and the
modifier category their targets live in, for a database whose schema was built from the
models without running migration 0334 (tests, a scratch schema): a migrated database gets
both from 0334, and the seeder never writes the category, which is content.
``get_maneuver_effect`` is how code finds one row, always by key and never by name.
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


def ensure_maneuver_effect_rows() -> list[ManeuverEffect]:
    """Get-or-create every catalog row with today's value.

    Idempotent. An edited base value is kept: only a missing row is written.
    """
    return [get_maneuver_effect(key) for key in ManeuverEffectKey]


def ensure_maneuver_effects() -> list[ManeuverEffect]:
    """Get-or-create every catalog row and the target category (see the module note)."""
    ModifierCategory.objects.get_or_create(
        name=MANEUVER_EFFECT_CATEGORY_NAME,
        defaults={"description": _CATEGORY_DESCRIPTION},
    )
    return ensure_maneuver_effect_rows()


def get_maneuver_effect(key: str) -> ManeuverEffect:
    """The catalog row for ``key``, written with its default if it is missing."""
    effect, _ = ManeuverEffect.objects.get_or_create(
        key=key, defaults={"base_value": MANEUVER_EFFECT_DEFAULTS[key]}
    )
    return effect
