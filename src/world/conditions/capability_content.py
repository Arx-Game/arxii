"""Idempotent seed for capability catalog rows used by actions.

Catalog data (no migration) — mirrors ``ensure_charm_content``.
"""

from __future__ import annotations

from world.conditions.models import CapabilityType

AT_WILL_SHIFTING = "at_will_shifting"


def ensure_at_will_shifting_capability() -> None:
    """Idempotently seed the at-will form-shift capability (#1604)."""
    CapabilityType.objects.get_or_create(
        name=AT_WILL_SHIFTING,
        defaults={
            "description": (
                "Grants the ability to shift into an owned alternate self at will, "
                "without a technique or trigger forcing the change."
            ),
            "innate_baseline": 0,
        },
    )
