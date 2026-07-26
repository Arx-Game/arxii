"""Service functions for the traits system (#2724).

Currently just the shared "ensure a STAT Trait exists" helper multiple
config-prerequisite paths (`world.fatigue`, `world.dreams`) need before the
content-fixture load populates `traits.trait`. See `STAT_TRAIT_DEFAULTS` in
`world.traits.constants`.
"""

from __future__ import annotations

from world.traits.constants import STAT_TRAIT_DEFAULTS
from world.traits.models import Trait


def ensure_stat_trait(name: str) -> Trait:
    """Ensure the named STAT Trait exists, creating it from STAT_TRAIT_DEFAULTS if not.

    A config prerequisite (#2724) may run before the content load populates the
    `traits.trait` content fixtures, so the underlying Trait row is get_or_create'd
    here rather than left to lazily self-heal at first gameplay use — a lazy self-heal
    would reinstate the undeclared-dependency bug #2724 exists to close (a config row
    stamped once, permanently, against a Trait that never got attached). The
    STAT_TRAIT_DEFAULTS values match the authored fixture rows exactly, so a later
    content-fixture upsert (`load_entries`) is a no-op.
    """
    trait_default = STAT_TRAIT_DEFAULTS[name]
    trait, _ = Trait.objects.get_or_create(
        name=name,
        defaults={
            "trait_type": trait_default.trait_type,
            "category": trait_default.category,
            "description": trait_default.description,
        },
    )
    return trait
