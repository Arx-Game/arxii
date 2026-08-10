"""Org pact vocabulary seeds (#2999) — PLACEHOLDER content."""

from __future__ import annotations

# name, allied_share_pct, income_share_pct, non_aggression, mutual_defense
_KINDS = [
    ("Defensive Compact", 40, 0, True, True),
    ("Trade Agreement", 10, 10, False, False),
    ("Non-Aggression Pact", 0, 0, True, False),
]


def ensure_pact_catalog() -> int:
    """Seed the PactKind lever catalog. Idempotent."""
    from world.societies.houses.models import PactKind  # noqa: PLC0415

    created = 0
    for name, allied, income, non_aggression, defense in _KINDS:
        _, was_created = PactKind.objects.update_or_create(
            name=name,
            defaults={
                "description": f"PLACEHOLDER {name} terms pending the content pass.",
                "allied_share_pct": allied,
                "income_share_pct": income,
                "non_aggression": non_aggression,
                "mutual_defense": defense,
            },
        )
        created += was_created
    return created
