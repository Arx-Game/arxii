"""Anima ritual resolver + menu contributor registration.

Registers the "anima_ritual" action_key with the scenes resolver registry.
On accept, applies the check outcome via apply_anima_ritual_outcome().
Contributes a menu entry per character's CharacterAnimaRitual (Phase 7 will
switch to known SCENE_ACTION rituals).
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

    Reads the initiator's CharacterAnimaRitual via the OneToOne reverse accessor on
    CharacterSheet.  Phase 7 will switch to reading from Ritual + RitualSceneActionConfig.
    """
    from world.magic.models.anima import CharacterAnimaRitual  # noqa: PLC0415
    from world.magic.services.anima import apply_anima_ritual_outcome  # noqa: PLC0415

    initiator_sheet = action_request.initiator_persona.character_sheet

    # OneToOne reverse — use getattr to avoid AttributeError on missing row.
    ritual: CharacterAnimaRitual | None = getattr(initiator_sheet, "anima_ritual", None)  # noqa: GETATTR_LITERAL
    if ritual is None:
        return  # silently no-op on malformed request

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
    """Contribute Anima Ritual entry when character has one configured.

    Once-per-scene cap can only be enforced when scene is provided.  Returns an
    empty list when scene is None or when the cap has already been spent.
    """
    from world.magic.models.anima import CharacterAnimaRitual  # noqa: PLC0415
    from world.magic.services.anima import has_performed_anima_ritual_in_scene  # noqa: PLC0415
    from world.scenes.action_availability import AvailableSceneAction  # noqa: PLC0415

    if scene is None:
        return []

    # Walk character → CharacterSheet via the anima_ritual reverse accessor.
    # character here is an ObjectDB; CharacterAnimaRitual.character is a FK to
    # CharacterSheet whose FK back to ObjectDB is CharacterSheet.character.
    try:
        ritual = CharacterAnimaRitual.objects.select_related("character").get(
            character__character=character,
        )
    except CharacterAnimaRitual.DoesNotExist:
        return []

    if has_performed_anima_ritual_in_scene(ritual=ritual, scene=scene):
        return []

    return [
        AvailableSceneAction(
            action_key="anima_ritual",
            action_template=None,
            enhancements=[],
            display_name="Anima Ritual",
            ritual_id=ritual.id,
        )
    ]


register_resolver("anima_ritual", _resolve_anima_ritual)
register_menu_contributor(_contribute_menu_entries)
