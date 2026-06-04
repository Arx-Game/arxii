from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from world.scenes.constants import SceneAction
from world.scenes.interaction_services import invalidate_active_scene_cache
from world.scenes.models import Persona, Scene

if TYPE_CHECKING:
    from typeclasses.characters import Character

ActionType = SceneAction


class MissingPrimaryPersonaError(LookupError):
    """A played Character is missing a CharacterSheet or PRIMARY persona.

    Per ``character_sheets/CLAUDE.md`` every played character has a
    CharacterSheet with a PRIMARY persona — that's a load-bearing repo
    invariant. Hitting this exception means something upstream broke that
    invariant (character_creation didn't finalize, test scaffolding skipped
    sheet setup, etc.) and we fail loud rather than silently bypass gates
    that depend on the persona.

    Lives here (not on ``npc_services``) because the resolver is general —
    NPCStanding, item-ownership audit snapshots, and mission flavor all
    want a PC's primary persona, and none of those callers should depend
    on the npc_services app.
    """

    def __init__(self, character: Character) -> None:
        super().__init__(
            f"Character {character!r} has no PRIMARY persona — required invariant "
            "(see character_sheets/CLAUDE.md). Check character_creation finalize "
            "or test setup."
        )
        self.character = character


def persona_for_character(character: Character) -> Persona:
    """Return the PC's PRIMARY persona; raise loud on missing sheet/persona.

    A played character without a sheet or PRIMARY persona is a programmer
    error per ``character_sheets/CLAUDE.md``; we surface that loudly rather
    than silently bypassing any gate that needs the persona (cooldown,
    standing, item ownership, etc.).
    """
    sheet = getattr(character, "sheet_data", None)  # noqa: GETATTR_LITERAL
    if sheet is None:
        raise MissingPrimaryPersonaError(character)
    try:
        return sheet.primary_persona
    except Exception as exc:
        raise MissingPrimaryPersonaError(character) from exc


def broadcast_scene_message(scene: Scene, action: ActionType) -> None:
    """Send scene information to all accounts in the scene's location.

    The room caches its active scene when a scene starts or ends so that
    subsequent room state payloads can avoid extra database lookups.

    Args:
        scene: Scene to announce.
        action: Event type for the scene.
    """
    location = scene.location
    if location is None:
        return
    if action in (SceneAction.START, SceneAction.END):
        invalidate_active_scene_cache(location)
        cast(Any, location).active_scene = scene if action == SceneAction.START else None
    for obj in location.contents:
        try:
            account = obj.account
        except AttributeError:
            continue
        is_owner = scene.is_owner(account)
        payload = {
            "action": action,
            "scene": {
                "id": scene.id,
                "name": scene.name,
                "description": scene.description,
                "is_owner": is_owner,
            },
        }
        account.msg(scene=((), payload))
