"""Idempotent seed for the 'Rite of Attunement' ritual (#707)."""

from __future__ import annotations

from world.magic.constants import ParticipationRule, RitualExecutionKind
from world.magic.models import Ritual

ATTUNEMENT_RITUAL_NAME = "Rite of Attunement"


def ensure_attunement_ritual() -> Ritual:
    """Get-or-create the 'Rite of Attunement' Ritual row.

    SERVICE-dispatched to ``world.magic.services.touchstones.attune_touchstone``.
    Binds a resonance-tied item to the performer; does not consume it.
    """
    ritual, _ = Ritual.objects.get_or_create(
        name=ATTUNEMENT_RITUAL_NAME,
        defaults={
            "description": (
                "Personally attune a resonance-tied item to yourself, binding it "
                "for future ritual use."
            ),
            "narrative_prose": (
                "You hold the item close and let your own resonance settle into "
                "it, thread by thread, until it answers to you alone."
            ),
            "hedge_accessible": True,
            "glimpse_eligible": False,
            "execution_kind": RitualExecutionKind.SERVICE,
            "service_function_path": "world.magic.services.touchstones.attune_touchstone",
            "participation_rule": ParticipationRule.SINGLE_ACTOR,
            "client_hosted": False,
        },
    )
    return ritual
