"""Seed the propaganda campaign-tier catalog (#1621).

Three PLACEHOLDER scales for the money→prestige sink — names, costs, and
magnitudes all pending an authoring/tuning pass. Upsert semantics
(``update_or_create`` keyed on ``name``) so edited seed values re-apply on
re-seed (#946).
"""

from __future__ import annotations

# (name, threshold_coppers, magnitude, display_order) — PLACEHOLDER values.
_TIERS: list[tuple[str, int, str, int]] = [
    ("Street Criers", 5_000, "small", 0),
    ("Broadsheet Campaign", 25_000, "moderate", 1),
    ("Grand Spectacle", 100_000, "high", 2),
]


def seed_propaganda_content() -> None:
    """Cluster entry — upsert the PLACEHOLDER campaign tiers."""
    from world.societies.constants import RenownMagnitude  # noqa: PLC0415
    from world.societies.models import PropagandaCampaignTier  # noqa: PLC0415

    valid = {choice.value for choice in RenownMagnitude}
    for name, cost, magnitude, order in _TIERS:
        PropagandaCampaignTier.objects.update_or_create(
            name=name,
            defaults={
                "threshold_coppers": cost,
                "magnitude": magnitude if magnitude in valid else RenownMagnitude.SMALL,
                "display_order": order,
                "is_active": True,
            },
        )
