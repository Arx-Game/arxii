"""Predator ecology seeds (#3093) — PLACEHOLDER content.

Predator kinds, one dormant demo band per defined realm anchor, and the
Affliction crisis vocabulary (deterrence-blind, spreading). All prose and
magnitudes PLACEHOLDER for Apostate's pass.
"""

from __future__ import annotations

# name, base_strength
_KINDS = [
    ("Bandit Company", 80),
    ("Pirate Fleet", 120),
    ("Raider Warband", 100),
]

# name, severity, spreads
_AFFLICTION_TYPES = [
    ("Walking Blight", "catastrophe", True),
    ("Whispering Rot", "crisis", True),
]


def ensure_predator_catalog() -> int:
    """Seed predator kinds + Affliction crisis types. Idempotent."""
    from world.predators.models import PredatorKind  # noqa: PLC0415
    from world.societies.houses.constants import CrisisAudience, CrisisValence  # noqa: PLC0415
    from world.societies.houses.models import DomainCrisisType  # noqa: PLC0415

    created = 0
    for name, base_strength in _KINDS:
        _, was_created = PredatorKind.objects.update_or_create(
            name=name,
            defaults={
                "description": f"PLACEHOLDER {name.lower()} flavor pending the content pass.",
                "base_strength": base_strength,
            },
        )
        created += was_created
    for name, severity, spreads in _AFFLICTION_TYPES:
        _, was_created = DomainCrisisType.objects.update_or_create(
            name=name,
            defaults={
                "description": f"PLACEHOLDER {name} stirs. The dead do not bargain.",
                "default_severity": severity,
                "automated": True,
                "valence": CrisisValence.THREAT,
                "audience": CrisisAudience.DOMAIN,
                "ignores_stature": True,
                "affliction_spreads": spreads,
            },
        )
        created += was_created
    return created
