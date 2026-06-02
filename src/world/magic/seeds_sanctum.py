"""Idempotent seeds for the Sanctum subsystem (Plan 4 §F).

Seeds the two Ritual rows (Homecoming + Purging) wired to the SERVICE
dispatch paths in ``world.magic.services.sanctum_rituals``. Per repo
discipline (#683): seeds live in code, called via ``get_or_create``.
NOT a committed fixture.
"""

from __future__ import annotations

from world.magic.constants import ParticipationRule, RitualExecutionKind
from world.magic.models import Ritual

HOMECOMING_RITUAL_NAME = "Ritual of Homecoming"
PURGING_RITUAL_NAME = "Ritual of Purging"


def ensure_homecoming_ritual() -> Ritual:
    """Get-or-create the Ritual of Homecoming row.

    Dispatches via ``world.magic.services.sanctum_rituals.perform_homecoming_ritual``
    at perform time. Single-actor (the leader) — covenant manager / personal
    owner per the service's own validation.
    """
    ritual, _ = Ritual.objects.get_or_create(
        name=HOMECOMING_RITUAL_NAME,
        defaults={
            "description": (
                "Consecrate a Sanctum by sacrificing your own resonance into "
                "its grown reservoir. The Sanctum's per-day income to woven "
                "weavers grows as you imbue more, capped per your Path level."
            ),
            "narrative_prose": (
                "You kneel at the heart of the Sanctum. Resonance unspools "
                "from your soul like silk and settles into the room's "
                "ambient pool, thickening it. The walls drink in your "
                "intention; the Sanctum knows you a little better."
            ),
            "hedge_accessible": False,
            "glimpse_eligible": False,
            "execution_kind": RitualExecutionKind.SERVICE,
            "service_function_path": (
                "world.magic.services.sanctum_rituals.perform_homecoming_ritual"
            ),
            "participation_rule": ParticipationRule.SINGLE_ACTOR,
            "client_hosted": True,
        },
    )
    return ritual


def ensure_purging_ritual() -> Ritual:
    """Get-or-create the Ritual of Purging row.

    Dispatches via ``world.magic.services.sanctum_rituals.perform_purging_ritual``.
    Changes the Sanctum's consecrated resonance type, draining grown
    resonance to a retention fraction.
    """
    ritual, _ = Ritual.objects.get_or_create(
        name=PURGING_RITUAL_NAME,
        defaults={
            "description": (
                "Re-consecrate a Sanctum to a different resonance type. "
                "Half of the imbued reservoir is destroyed; surviving threads "
                "adopt the new type."
            ),
            "narrative_prose": (
                "You burn the old pattern out of the Sanctum's bones. "
                "Resonance gutters and reignites in a foreign key. The room "
                "is the same room — and a different one."
            ),
            "hedge_accessible": False,
            "glimpse_eligible": False,
            "execution_kind": RitualExecutionKind.SERVICE,
            "service_function_path": (
                "world.magic.services.sanctum_rituals.perform_purging_ritual"
            ),
            "participation_rule": ParticipationRule.SINGLE_ACTOR,
            "client_hosted": True,
        },
    )
    return ritual


def ensure_sanctum_rituals() -> None:
    """Seed both Sanctum rituals. Safe to call repeatedly."""
    ensure_homecoming_ritual()
    ensure_purging_ritual()
