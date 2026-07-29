"""Proclamation stance archetypes + edict kinds (#2842).

PLACEHOLDER vectors and payloads — Apostate to tune. Authoritative on
reseed (update_or_create) so tuning lands without row churn.
"""

from __future__ import annotations

# name -> (deltas dict, description). Same axis conventions as scandal_archetypes.
_STANCE_ARCHETYPES: dict[str, tuple[dict[str, int], str]] = {
    "Defense of the Old Ways": (
        {"change_delta": -3, "method_delta": 2, "allegiance_delta": -1},
        "A call to preserve the forms and customs that have held the world together.",
    ),
    "Mercy for the Fallen": (
        {"mercy_delta": 3, "status_delta": 1},
        "Plea for clemency toward the defeated and the destitute.",
    ),
    "The Strong Hand": (
        {"power_delta": -2, "mercy_delta": -1, "method_delta": 1},
        "An argument for firm rule and the hierarchies that keep order.",
    ),
    "Bread and Circuses": (
        {"mercy_delta": 1, "status_delta": -1, "power_delta": 1},
        "Promise of provision and spectacle for the common folk.",
    ),
    "The Open Road": (
        {"change_delta": 2, "allegiance_delta": 2, "method_delta": -1},
        "A declaration favoring progress, trade, and freedom of movement.",
    ),
    "Honor Above All": (
        {"method_delta": 3, "allegiance_delta": -2},
        "A vow that the sworn word and the old codes are the only law worth keeping.",
    ),
    "The Reckoning": (
        {"mercy_delta": -2, "status_delta": -2, "change_delta": 1},
        "A warning that the corrupt and complacent will be called to account.",
    ),
    "Unity of the Realm": (
        {"allegiance_delta": -3, "power_delta": -1, "mercy_delta": 1},
        "A call for solidarity under the crown, setting aside factional grievance.",
    ),
    "The Free Hand": (
        {"power_delta": 2, "allegiance_delta": 1, "change_delta": 1},
        "An argument that the gifted and ambitious should be unshackled to act.",
    ),
}

# name -> (description, stance_name, payload dict)
_EDICT_KINDS: dict[str, tuple[str, str, dict[str, int]]] = {
    "Squeeze the Taxes": (
        "Raise the tax rate on all domain income.",
        "The Strong Hand",
        {"income_gross_pct": 20, "weekly_unrest_delta": 5, "weekly_upkeep_coppers": 0},
    ),
    "Bread and Circuses": (
        "Spend on provisions and spectacle to keep the populace content.",
        "Bread and Circuses",
        {"income_gross_pct": -10, "weekly_unrest_delta": -5, "weekly_upkeep_coppers": 100},
    ),
    "Doubled Patrols": (
        "Increase patrols and enforcement across the domain.",
        "The Strong Hand",
        {"income_gross_pct": 0, "weekly_unrest_delta": -3, "weekly_upkeep_coppers": 200},
    ),
    "Open the Granaries": (
        "Release stored grain to feed the populace.",
        "Mercy for the Fallen",
        {"income_gross_pct": -15, "weekly_unrest_delta": -8, "weekly_upkeep_coppers": 50},
    ),
    "Court the Guilds": (
        "Offer favorable terms to guilds and traders.",
        "The Open Road",
        {"income_gross_pct": 10, "weekly_unrest_delta": 0, "weekly_upkeep_coppers": 0},
    ),
    "Iron Curfew": (
        "Impose a strict curfew and restrict movement.",
        "Defense of the Old Ways",
        {"income_gross_pct": -5, "weekly_unrest_delta": 3, "weekly_upkeep_coppers": 150},
    ),
}


def seed_proclamations() -> None:
    """Idempotent + authoritative on vectors/payloads (tweaks land on reseed)."""
    from world.proclamations.models import EdictKind, StanceArchetype  # noqa: PLC0415

    for name, (deltas, description) in _STANCE_ARCHETYPES.items():
        StanceArchetype.objects.update_or_create(
            name=name,
            defaults={"description": description, **deltas},
        )

    for name, (description, stance_name, payload) in _EDICT_KINDS.items():
        stance = StanceArchetype.objects.filter(name=stance_name).first()
        if stance is None:
            continue
        EdictKind.objects.update_or_create(
            name=name,
            defaults={"description": description, "stance": stance, **payload},
        )
