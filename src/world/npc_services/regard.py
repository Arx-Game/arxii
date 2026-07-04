"""Read helper for the NpcRegard opinion axis (#1717).

One axis, one small module — mirrors ``world.npc_services.allegiance``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.scenes.models import Persona
    from world.societies.models import Organization, Society


def get_regard(holder_persona: Persona, target: Persona | Organization | Society) -> int:
    """Signed opinion ``holder_persona`` holds of ``target``; 0 if no active row."""
    from world.npc_services.models import NpcRegard  # noqa: PLC0415
    from world.scenes.models import Persona as PersonaModel  # noqa: PLC0415
    from world.societies.models import Organization, Society  # noqa: PLC0415

    if isinstance(target, PersonaModel):
        column = "target_persona"
    elif isinstance(target, Organization):
        column = "target_organization"
    elif isinstance(target, Society):
        column = "target_society"
    else:
        msg = f"Unsupported NpcRegard target type: {type(target)!r}"
        raise TypeError(msg)

    row = NpcRegard.objects.filter(
        holder_persona=holder_persona,
        ended_at__isnull=True,
        **{column: target},
    ).first()
    return row.value if row is not None else 0
