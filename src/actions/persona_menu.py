"""The persona menu (#4030): what a viewer can do to one persona, and why not.

Composed server-side from each action's own prerequisites (``Action.check_availability``)
so the menu and ``run()`` share one check and the menu never offers what the action then
refuses. Replaces the unfinished 2025 per-entity command list (``BaseState.dispatcher_tags``
and the room-state ``commands`` field). See ADR-4030.

Privacy: every reason is the action's own refusal text, which never names a masked
target's real key; Look's reason is the same for an absent and a concealed target.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist

from actions.constants import PersonaMenuGroupKey
from actions.definitions.perception import LOOK_NOT_VISIBLE_MESSAGE, look_target_visible
from actions.registry import get_action
from actions.types import PersonaMenu, PersonaMenuGroup, PersonaMenuItem

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.scenes.models import Persona, Scene

LOOK_UNAVAILABLE = LOOK_NOT_VISIBLE_MESSAGE
TREAT_UNAVAILABLE = "Nothing you can treat on them right now."
BLOCK_UNAVAILABLE = "You need a face in play to block someone."
SCENE_EMPTY_STATE = (
    "Scene actions (Treat, Succor, Interpose, techniques) show here once a scene is running."
)
SELF_NOTICE = "Nothing here targets yourself. Your own actions are in the Actions panel."


def build_persona_menu(actor: ObjectDB, persona: Persona) -> PersonaMenu:
    """Compose the menu ``actor`` sees for ``persona``."""
    target = persona.character_sheet.character
    viewer_persona = _viewer_persona(actor)
    look = _look_item(actor, target)
    if target.pk == actor.pk:
        return PersonaMenu(
            persona=persona,
            is_self=True,
            scene=None,
            viewer_persona=viewer_persona,
            items=[look],
            groups=[PersonaMenuGroup(key=PersonaMenuGroupKey.PERCEPTION)],
            scene_actions=[],
            notice=SELF_NOTICE,
        )

    if not look.available:
        # #4030 fix wave (controller ruling): an unseen target — concealed or simply
        # not co-located, worded identically — must be indistinguishable from an
        # absent one. Every other item's own prerequisite checks room equality, not
        # perception, so composing them here would leak "this persona pk exists and
        # is nearby" through Challenge/Identify/scene availability even when Look
        # itself refuses. Return the same shape a genuinely-elsewhere target gets.
        return PersonaMenu(
            persona=persona,
            is_self=False,
            scene=None,
            viewer_persona=viewer_persona,
            items=[look, *_social_items(viewer_persona)],
            groups=[
                PersonaMenuGroup(key=PersonaMenuGroupKey.PERCEPTION),
                PersonaMenuGroup(key=PersonaMenuGroupKey.SOCIAL),
            ],
            scene_actions=[],
        )

    scene = _shared_scene(actor, target)
    items = [
        look,
        # #4030 fix wave (demo-order controller ruling): Identify sits with Challenge
        # in the conflict group, right after it -- Look | Challenge, Identify | scene
        # items | Mute, Block. Its own availability/reason is unchanged.
        _registry_item(
            actor,
            "challenge",
            "Challenge to a duel",
            PersonaMenuGroupKey.CONFLICT,
            {"target": persona.pk},
        ),
        _registry_item(
            actor,
            "identify",
            "Identify",
            PersonaMenuGroupKey.CONFLICT,
            {"target_persona_id": persona.pk},
        ),
    ]
    scene_actions = []
    if scene is not None:
        items += [
            _registry_item(
                actor,
                "scene_succor",
                "Succor (shelter from hazards)",
                PersonaMenuGroupKey.SCENE,
                {"target_persona_id": persona.pk},
            ),
            _registry_item(
                actor,
                "scene_interpose",
                "Interpose (guard from harm)",
                PersonaMenuGroupKey.SCENE,
                {"target_persona_id": persona.pk},
            ),
            _treat_item(actor, persona, scene),
        ]
        if _viewer_can_gm(actor, scene):
            items.append(
                PersonaMenuItem(
                    key="give_mission",
                    label="Give mission…",
                    group=PersonaMenuGroupKey.SCENE,
                    available=True,
                )
            )
        scene_actions = _targeted_scene_actions(actor)
    items += _social_items(viewer_persona)
    groups = [
        PersonaMenuGroup(key=PersonaMenuGroupKey.PERCEPTION),
        PersonaMenuGroup(key=PersonaMenuGroupKey.CONFLICT),
        PersonaMenuGroup(
            key=PersonaMenuGroupKey.SCENE,
            empty_state="" if scene is not None else SCENE_EMPTY_STATE,
        ),
        PersonaMenuGroup(key=PersonaMenuGroupKey.SOCIAL),
    ]
    return PersonaMenu(
        persona=persona,
        is_self=False,
        scene=scene,
        viewer_persona=viewer_persona,
        items=items,
        groups=groups,
        scene_actions=scene_actions,
    )


def _registry_item(
    actor: ObjectDB, key: str, label: str, group: str, kwargs: dict[str, object]
) -> PersonaMenuItem:
    availability = get_action(key).check_availability(actor, context={"kwargs": kwargs})
    return PersonaMenuItem(
        key=key,
        label=label,
        group=group,
        available=availability.available,
        reason="" if availability.available else availability.reasons[0],
    )


def _look_item(actor: ObjectDB, target: ObjectDB) -> PersonaMenuItem:
    visible = look_target_visible(actor, target)
    return PersonaMenuItem(
        key="look",
        label="Look",
        group=PersonaMenuGroupKey.PERCEPTION,
        available=visible,
        reason="" if visible else LOOK_UNAVAILABLE,
    )


def _social_items(viewer_persona: Persona | None) -> list[PersonaMenuItem]:
    """``mute``/``block`` — always offered on a visible-or-absent-alike target."""
    return [
        PersonaMenuItem(key="mute", label="Mute", group=PersonaMenuGroupKey.SOCIAL, available=True),
        PersonaMenuItem(
            key="block",
            label="Block…",
            group=PersonaMenuGroupKey.SOCIAL,
            available=viewer_persona is not None,
            reason="" if viewer_persona is not None else BLOCK_UNAVAILABLE,
        ),
    ]


def _shared_scene(actor: ObjectDB, target: ObjectDB) -> Scene | None:
    from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

    room = actor.db_location
    if room is None or target.db_location != room:
        return None
    return get_active_scene(room)


def _treat_item(actor: ObjectDB, persona: Persona, scene: Scene) -> PersonaMenuItem:
    from world.conditions.services import get_treatment_candidates  # noqa: PLC0415

    helper_sheet = _sheet(actor)
    candidates = (
        get_treatment_candidates(helper_sheet, persona.character_sheet, scene)
        if helper_sheet is not None
        else []
    )
    return PersonaMenuItem(
        key="treat",
        label="Treat…",
        group=PersonaMenuGroupKey.SCENE,
        available=bool(candidates),
        reason="" if candidates else TREAT_UNAVAILABLE,
    )


def _viewer_can_gm(actor: ObjectDB, scene: Scene) -> bool:
    """The rule behind the scene payload's ``viewer_can_gm`` (world.scenes.serializers)."""
    account = actor.account
    if account is None:
        return False
    return bool(account.is_staff or scene.is_gm(account) or scene.is_owner(account))


def _targeted_scene_actions(actor: ObjectDB) -> list:
    """The viewer's own targeted actions (the list the scene menu has always shown)."""
    from actions.player_interface import get_player_actions  # noqa: PLC0415

    return [a for a in get_player_actions(actor) if a.target_spec is not None]


def _viewer_persona(actor: ObjectDB) -> Persona | None:
    from world.scenes.models import Persona  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    sheet = _sheet(actor)
    if sheet is None:
        return None
    try:
        return active_persona_for_sheet(sheet)
    except Persona.DoesNotExist:
        return None


def _sheet(actor: ObjectDB) -> CharacterSheet | None:
    try:
        return actor.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return None
