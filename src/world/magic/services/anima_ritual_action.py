"""Anima ritual resolver registration.

Registers the "anima_ritual" action_key with the scenes resolver registry.
On accept, applies the check outcome via apply_anima_ritual_outcome().
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.magic.models import CharacterAnima
from world.scenes.action_resolvers import register_resolver

if TYPE_CHECKING:
    from world.scenes.action_models import SceneActionRequest
    from world.scenes.types import EnhancedSceneActionResult


def _resolve_anima_ritual(
    action_request: SceneActionRequest,
    result: EnhancedSceneActionResult,
) -> None:
    """Apply anima ritual outcome when an accepted request has action_key='anima_ritual'.

    Reads the Ritual from action_request.snapshot_ritual (populated at request
    creation time). Falls back to looking up the initiator's authored SCENE_ACTION
    Ritual when snapshot_ritual is absent (legacy requests).
    """
    from world.magic.constants import RitualExecutionKind  # noqa: PLC0415
    from world.magic.models.rituals import Ritual  # noqa: PLC0415
    from world.magic.services.anima import apply_anima_ritual_outcome  # noqa: PLC0415

    initiator_sheet = action_request.initiator_persona.character_sheet

    # Prefer the snapshot copy; fall back to live authorship lookup.
    ritual = action_request.snapshot_ritual
    if ritual is None:
        ritual = (
            Ritual.objects.filter(
                author_account=initiator_sheet.character.db_account,
                execution_kind=RitualExecutionKind.SCENE_ACTION,
            )
            .select_related("check_config")
            .first()
        )

    if ritual is None:
        return  # silently no-op on malformed request

    # Ensure the config is loaded (may already be via select_related above).
    try:
        _ = ritual.check_config
    except Exception:  # noqa: BLE001
        return  # SCENE_ACTION ritual missing config — silently skip

    main_result = result.action_resolution.main_result
    if main_result is None or main_result.check_result is None:
        return  # no check outcome to apply

    outcome = main_result.check_result.outcome

    ritual_outcome = apply_anima_ritual_outcome(
        ritual=ritual,
        outcome=outcome,
        scene=action_request.scene,
        character_sheet=initiator_sheet,
    )

    # Attach a transient payload so the response serializer can include
    # anima_recovery for the initiator without a second DB query.
    anima = CharacterAnima.objects.get(character=initiator_sheet.character)
    action_request._anima_recovery_payload = {  # noqa: SLF001
        "recovered": ritual_outcome.anima_recovered,
        "soulfray_reduced": ritual_outcome.severity_reduced,
        "new_pool": anima.current,
    }


register_resolver("anima_ritual", _resolve_anima_ritual)
