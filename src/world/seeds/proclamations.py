"""Stance + edict catalogs (#2842) — PLACEHOLDER content for Apostate's pass.

Stances are positions someone stands FOR (sibling vocabulary to the scandal
archetypes' deed-judgments). Axis magnitudes follow the ±2-typical rule.
"""

from __future__ import annotations

_STRONG_HAND_STANCE = "The Strong Hand"

# name, description, axis deltas (mercy, method, status, change, allegiance, power)
_STANCES = [
    (
        "Defense of the Old Ways",
        "PLACEHOLDER The old forms held us together; they still do.",
        {"change_delta": -2, "method_delta": 1},
    ),
    (
        "The Reformer's Call",
        "PLACEHOLDER What was built can be built better.",
        {"change_delta": 2, "status_delta": -1},
    ),
    (
        "Mercy for the Fallen",
        "PLACEHOLDER No one is beyond redemption who asks for it.",
        {"mercy_delta": 2, "power_delta": 1},
    ),
    (
        _STRONG_HAND_STANCE,
        "PLACEHOLDER Order is a kindness; enforce it.",
        {"mercy_delta": -2, "power_delta": -2},
    ),
    (
        "Honor Before Advantage",
        "PLACEHOLDER A bought victory costs more than a clean defeat.",
        {"method_delta": 2},
    ),
    (
        "Whatever It Takes",
        "PLACEHOLDER Results forgive their methods.",
        {"method_delta": -2, "status_delta": -1},
    ),
    (
        "The Common Table",
        "PLACEHOLDER High and low eat from the same harvest.",
        {"power_delta": 2, "mercy_delta": 1},
    ),
    (
        "Blood and Banner",
        "PLACEHOLDER Loyalty to one's own, before all else.",
        {"allegiance_delta": -2},
    ),
    (
        "The Open Road",
        "PLACEHOLDER No oath outranks a free conscience.",
        {"allegiance_delta": 2, "change_delta": 1},
    ),
]

# name, description, stance name, income_pct, weekly_unrest, weekly_upkeep
_EDICT_KINDS = [
    (
        "Squeeze the Taxes",
        "PLACEHOLDER The assessors visit twice; the ledgers gain weight.",
        "Whatever It Takes",
        25,
        3,
        0,
    ),
    (
        "Bread and Circuses",
        "PLACEHOLDER Feasts and games; the commons cheer, the coffers sigh.",
        "The Common Table",
        -10,
        -4,
        2_000,
    ),
    (
        "Doubled Patrols",
        "PLACEHOLDER Steel on every road; little moves unseen.",
        _STRONG_HAND_STANCE,
        -5,
        1,
        1_500,
    ),
    (
        "Open the Granaries",
        "PLACEHOLDER No one hungers under this roof.",
        "Mercy for the Fallen",
        -10,
        -5,
        1_000,
    ),
    (
        "Court the Guilds",
        "PLACEHOLDER Charters and favors for the makers and sellers.",
        "The Reformer's Call",
        15,
        1,
        500,
    ),
    (
        "Iron Curfew",
        "PLACEHOLDER The streets empty at dusk, by order.",
        _STRONG_HAND_STANCE,
        -10,
        4,
        500,
    ),
]


def ensure_stance_archetypes() -> int:
    """Seed the stance vocabulary. Idempotent; returns rows created."""
    from world.societies.models import StanceArchetype  # noqa: PLC0415

    created = 0
    for name, description, axes in _STANCES:
        _, was_created = StanceArchetype.objects.get_or_create(
            name=name, defaults={"description": description, **axes}
        )
        created += int(was_created)
    return created


def ensure_edict_kinds() -> int:
    """Seed the standing-policy catalog. Idempotent; returns rows created."""
    from world.societies.houses.models import EdictKind  # noqa: PLC0415
    from world.societies.models import StanceArchetype  # noqa: PLC0415

    ensure_stance_archetypes()
    created = 0
    for name, description, stance_name, income_pct, unrest, upkeep in _EDICT_KINDS:
        stance = StanceArchetype.objects.get(name=stance_name)
        _, was_created = EdictKind.objects.get_or_create(
            name=name,
            defaults={
                "description": description,
                "stance": stance,
                "income_gross_pct": income_pct,
                "weekly_unrest_delta": unrest,
                "weekly_upkeep_coppers": upkeep,
            },
        )
        created += int(was_created)
    return created
