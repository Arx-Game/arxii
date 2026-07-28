"""Crisis catalog seed (#2837) — PLACEHOLDER content.

The DomainCrisisType/Option machinery shipped with #2238 but no catalog ever
existed, so every generated crisis spawned typeless with no judgment call to
make. This seeds the threat/opportunity vocabulary across all three audiences
(domain, any org, criminal org) so the weekly generation tick, the covert
window, and the spy counterplay kit all have something to chew on.

MISSION options bind to an existing active MissionTemplate when one is seeded
(PLACEHOLDER binding — the content pass authors real per-type missions);
shards without mission content just get the PAY/WAIT menu. All prose and
magnitudes are PLACEHOLDER for Apostate's pass.
"""

from __future__ import annotations

from world.societies.houses.constants import (
    CrisisAudience,
    CrisisResolutionKind,
    CrisisValence,
    DomainCrisisSeverity,
)

# name, audience, valence, severity, description, [option kinds]
_CATALOG = [
    # --- Domain threats ---
    (
        "Bandit Camp",
        CrisisAudience.DOMAIN,
        CrisisValence.THREAT,
        DomainCrisisSeverity.TROUBLE,
        "PLACEHOLDER Riders on the far road; carts arrive lighter than they left.",
        [CrisisResolutionKind.PAY, CrisisResolutionKind.MISSION, CrisisResolutionKind.WAIT],
    ),
    (
        "Grain Blight",
        CrisisAudience.DOMAIN,
        CrisisValence.THREAT,
        DomainCrisisSeverity.CRISIS,
        "PLACEHOLDER A grey mold walks the rows faster than the reapers do.",
        [CrisisResolutionKind.PAY, CrisisResolutionKind.WAIT],
    ),
    (
        "Corrupt Steward",
        CrisisAudience.DOMAIN,
        CrisisValence.THREAT,
        DomainCrisisSeverity.TROUBLE,
        "PLACEHOLDER The ledgers balance beautifully. The granary does not.",
        [CrisisResolutionKind.PAY, CrisisResolutionKind.MISSION, CrisisResolutionKind.WAIT],
    ),
    (
        "Road Washout",
        CrisisAudience.DOMAIN,
        CrisisValence.THREAT,
        DomainCrisisSeverity.TROUBLE,
        "PLACEHOLDER The spring melt took the bridge, and trade takes the long way.",
        [CrisisResolutionKind.PAY, CrisisResolutionKind.WAIT],
    ),
    # --- Domain opportunities ---
    (
        "Mis-routed Caravan",
        CrisisAudience.DOMAIN,
        CrisisValence.OPPORTUNITY,
        DomainCrisisSeverity.TROUBLE,
        "PLACEHOLDER A rich caravan waits out repairs on your roads — hospitality pays.",
        [CrisisResolutionKind.MISSION, CrisisResolutionKind.WAIT],
    ),
    (
        "Vein Struck",
        CrisisAudience.DOMAIN,
        CrisisValence.OPPORTUNITY,
        DomainCrisisSeverity.CRISIS,
        "PLACEHOLDER A quarry crew broke into something that glitters. Word will spread.",
        [CrisisResolutionKind.MISSION, CrisisResolutionKind.WAIT],
    ),
    # --- Org threats (any organization) ---
    (
        "Poached Patrons",
        CrisisAudience.ORG,
        CrisisValence.THREAT,
        DomainCrisisSeverity.TROUBLE,
        "PLACEHOLDER A rival courts your best customers with suspiciously good terms.",
        [CrisisResolutionKind.PAY, CrisisResolutionKind.WAIT],
    ),
    (
        "Ledger Rot",
        CrisisAudience.ORG,
        CrisisValence.THREAT,
        DomainCrisisSeverity.CRISIS,
        "PLACEHOLDER Somewhere between the counting house and the vault, coin evaporates.",
        [CrisisResolutionKind.PAY, CrisisResolutionKind.MISSION, CrisisResolutionKind.WAIT],
    ),
    # --- Org opportunities ---
    (
        "Rival's Ledger Exposed",
        CrisisAudience.ORG,
        CrisisValence.OPPORTUNITY,
        DomainCrisisSeverity.TROUBLE,
        "PLACEHOLDER A clerk with a grudge is selling a competitor's books. Briefly.",
        [CrisisResolutionKind.MISSION, CrisisResolutionKind.WAIT],
    ),
    (
        "Desperate Defector",
        CrisisAudience.ORG,
        CrisisValence.OPPORTUNITY,
        DomainCrisisSeverity.CRISIS,
        "PLACEHOLDER Someone senior wants out of somewhere dangerous, and will pay in secrets.",
        [CrisisResolutionKind.MISSION, CrisisResolutionKind.WAIT],
    ),
    # --- Criminal org threats ---
    (
        "Magistrate's Eye",
        CrisisAudience.CRIMINAL_ORG,
        CrisisValence.THREAT,
        DomainCrisisSeverity.CRISIS,
        "PLACEHOLDER A magistrate has taken a professional interest in your streets.",
        [CrisisResolutionKind.PAY, CrisisResolutionKind.MISSION, CrisisResolutionKind.WAIT],
    ),
    (
        "Informer in the Ranks",
        CrisisAudience.CRIMINAL_ORG,
        CrisisValence.THREAT,
        DomainCrisisSeverity.TROUBLE,
        "PLACEHOLDER Jobs keep going wrong in ways only an insider could arrange.",
        [CrisisResolutionKind.MISSION, CrisisResolutionKind.WAIT],
    ),
    # --- Criminal org opportunities ---
    (
        "Unguarded Shipment",
        CrisisAudience.CRIMINAL_ORG,
        CrisisValence.OPPORTUNITY,
        DomainCrisisSeverity.TROUBLE,
        "PLACEHOLDER A warehouse clerk forgot to hire the second watchman. Tonight.",
        [CrisisResolutionKind.MISSION, CrisisResolutionKind.WAIT],
    ),
    (
        "Rival Crew Leaderless",
        CrisisAudience.CRIMINAL_ORG,
        CrisisValence.OPPORTUNITY,
        DomainCrisisSeverity.CRISIS,
        "PLACEHOLDER Their boss is in a cell and their soldiers are taking offers.",
        [CrisisResolutionKind.MISSION, CrisisResolutionKind.WAIT],
    ),
]

# PLACEHOLDER base PAY cost; severity multiplies at runtime (crisis_services).
_PAY_BASE_COPPERS = 2_000
_WAIT_SELF_RESOLVE_PCT = 20
_WAIT_WORSEN_PCT = 15


def _placeholder_mission_template():
    from world.missions.models import MissionTemplate  # noqa: PLC0415

    return MissionTemplate.objects.filter(is_active=True).first()


def ensure_crisis_catalog() -> int:
    """Seed the threat/opportunity catalog. Idempotent; returns types created."""
    from world.societies.houses.models import (  # noqa: PLC0415
        DomainCrisisType,
        DomainCrisisTypeOption,
    )

    mission_template = _placeholder_mission_template()
    created_count = 0
    for name, audience, valence, severity, description, option_kinds in _CATALOG:
        crisis_type, created = DomainCrisisType.objects.get_or_create(
            name=name,
            defaults={
                "description": description,
                "default_severity": severity,
                "automated": True,
                "spawn_weight": 10,
                "valence": valence,
                "audience": audience,
            },
        )
        created_count += int(created)
        for kind in option_kinds:
            if kind == CrisisResolutionKind.MISSION and mission_template is None:
                continue  # contentless shard: menu degrades to PAY/WAIT
            defaults = {}
            if kind == CrisisResolutionKind.PAY:
                defaults["cost_coppers"] = _PAY_BASE_COPPERS
            elif kind == CrisisResolutionKind.MISSION:
                defaults["mission_template"] = mission_template
            elif kind == CrisisResolutionKind.WAIT:
                defaults["self_resolve_pct"] = _WAIT_SELF_RESOLVE_PCT
                defaults["worsen_pct"] = _WAIT_WORSEN_PCT
            DomainCrisisTypeOption.objects.get_or_create(
                crisis_type=crisis_type, kind=kind, defaults=defaults
            )
    return created_count
