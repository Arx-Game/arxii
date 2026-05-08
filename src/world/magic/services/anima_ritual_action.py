"""Anima ritual resolver + menu contributor registration.

Registers the "anima_ritual" action_key with the scenes resolver registry.
On accept, applies the check outcome via apply_anima_ritual_outcome().
Contributes a menu entry per character's known SCENE_ACTION Ritual.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.scenes.action_resolvers import register_menu_contributor, register_resolver

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.scenes.action_availability import AvailableSceneAction
    from world.scenes.action_models import SceneActionRequest
    from world.scenes.models import Scene
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
            .select_related("scene_action_config")
            .first()
        )

    if ritual is None:
        return  # silently no-op on malformed request

    # Ensure the sidecar is loaded (may already be via select_related above).
    try:
        _ = ritual.scene_action_config
    except Exception:  # noqa: BLE001
        return  # SCENE_ACTION ritual missing sidecar — silently skip

    main_result = result.action_resolution.main_result
    if main_result is None or main_result.check_result is None:
        return  # no check outcome to apply

    outcome = main_result.check_result.outcome

    apply_anima_ritual_outcome(
        ritual=ritual,
        outcome=outcome,
        scene=action_request.scene,
        character_sheet=initiator_sheet,
    )


def _contribute_menu_entries(
    character: ObjectDB,
    scene: Scene | None,
) -> list[AvailableSceneAction]:
    """Contribute Anima Ritual entries for all known SCENE_ACTION rituals.

    Gated by CharacterRitualKnowledge so authorship and teaching are unified.
    Once-per-scene cap can only be enforced when scene is provided. Returns an
    empty list when scene is None or when the cap has already been spent.
    """
    from world.magic.constants import RitualExecutionKind  # noqa: PLC0415
    from world.magic.models.knowledge import CharacterRitualKnowledge  # noqa: PLC0415
    from world.magic.services.anima import has_performed_anima_ritual_in_scene  # noqa: PLC0415
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.scenes.action_availability import AvailableSceneAction  # noqa: PLC0415

    if scene is None:
        return []

    try:
        roster_entry = RosterEntry.objects.get(character_sheet__character=character)
    except RosterEntry.DoesNotExist:
        return []

    ritual_qs = [
        krec.ritual
        for krec in CharacterRitualKnowledge.objects.filter(
            roster_entry=roster_entry,
            ritual__execution_kind=RitualExecutionKind.SCENE_ACTION,
        ).select_related("ritual__scene_action_config")
    ]

    entries = []
    for ritual in ritual_qs:
        if has_performed_anima_ritual_in_scene(ritual=ritual, scene=scene):
            continue
        entries.append(
            AvailableSceneAction(
                action_key="anima_ritual",
                action_template=None,
                enhancements=[],
                display_name=f"Anima Ritual: {ritual.name}",
                ritual_id=ritual.id,
            )
        )
    return entries


register_resolver("anima_ritual", _resolve_anima_ritual)
register_menu_contributor(_contribute_menu_entries)
