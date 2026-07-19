"""GM improv prop-staging actions (#2503) — "are there torches in here?" made real.

Mid-scene, a GM materializes a curated ``ItemTemplate`` as a physical prop in the
room (``StagePropAction``) or tags an existing object with a curated ``Property``
(``StagePropertyAction``). Both are name-curated (existing catalog rows only,
resolved by exact pk-or-name via ``resolve_model_by_pk_or_name`` — no freeform
creation) and gated to the room's active scene GM/owner or staff, mirroring
``dramatic_moments.py``'s ``_account_can_gm_scene`` predicate (staff, or
``scene.is_gm``/``scene.is_owner``) resolved from the room's active scene via
``world.scenes.interaction_services.get_active_scene`` — the same room-scoped
scene resolver ``endorse.py``/``react.py`` use.

A staged prop rides the same materialization chokepoint Task 2 built
(``world.items.services.materialize.materialize_item_game_object_in_room``), so
it carries its template's default ``ObjectProperty`` rows and is immediately
visible to Task 3's bare-object ``get_available_actions`` scan — no extra wiring.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from actions.base import Action
from actions.types import ActionResult, TargetType
from commands.exceptions import CommandError
from commands.utils.gm_resolution import resolve_account_or_none, resolve_model_by_pk_or_name

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

_MSG_GM_ONLY = "Only the scene's GM, owner, or staff may stage a prop."
_MSG_NO_TEMPLATE = "Which item template? Provide its name."
_MSG_NO_PROPERTY = "Which property? Provide its name."
_MSG_NO_ROOM = "You have no location to stage a prop in."


def _account_can_gm_room(actor: ObjectDB, account: AccountDB | None) -> bool:
    """True when ``account`` is staff, or the GM/owner of the actor's room's active scene."""
    from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

    if account is None:
        return False
    if account.is_staff:
        return True
    scene = get_active_scene(actor.location)
    if scene is None:
        return False
    return bool(scene.is_gm(account) or scene.is_owner(account))


def _resolve_target_obj(actor: ObjectDB, kwargs: dict[str, Any]) -> ObjectDB | None:
    """Resolve the ``target`` kwarg -- ObjectDB (telnet) or ``target_id`` int (web).

    Falls back to the actor's own room (staging a property on the room itself —
    "this room is dark") when neither is supplied. Scoped to the actor's current
    location for the ``target_id`` case so a GM can't tag an object elsewhere.
    """
    target = kwargs.get("target")
    if target is not None and hasattr(target, "pk"):
        return target
    target_id = kwargs.get("target_id")
    if target_id is not None:
        from evennia.objects.models import ObjectDB as _ObjectDB  # noqa: PLC0415

        return _ObjectDB.objects.filter(pk=target_id, db_location=actor.location).first()
    return actor.location


@dataclass
class StagePropAction(Action):
    """GM improv: instantiate a curated ``ItemTemplate`` as a physical prop, here."""

    key: str = "stage_prop"
    name: str = "Stage Prop"
    icon: str = "sparkles"
    category: str = "items"
    target_type: TargetType = TargetType.SELF

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from world.items.models import ItemTemplate  # noqa: PLC0415
        from world.items.services.staging import stage_prop  # noqa: PLC0415

        account = resolve_account_or_none(actor)
        if not _account_can_gm_room(actor, account):
            return ActionResult(success=False, message=_MSG_GM_ONLY)

        template_name = kwargs.get("item_template")
        if not template_name:
            return ActionResult(success=False, message=_MSG_NO_TEMPLATE)
        try:
            template = resolve_model_by_pk_or_name(
                ItemTemplate,
                str(template_name),
                not_found_msg=f"No item template named {template_name!r}.",
            )
        except CommandError as exc:
            return ActionResult(success=False, message=str(exc))

        room = actor.location
        if room is None:
            return ActionResult(success=False, message=_MSG_NO_ROOM)

        game_object = stage_prop(template, room)
        return ActionResult(
            success=True,
            message=f"You conjure {game_object.db_key} into being.",
            data={"object_id": game_object.pk},
        )


@dataclass
class StagePropertyAction(Action):
    """GM improv: attach/refresh a curated ``Property`` on an object in the room."""

    key: str = "stage_property"
    name: str = "Stage Property"
    icon: str = "tag"
    category: str = "items"
    target_type: TargetType = TargetType.SINGLE
    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target"})

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from world.mechanics.models import Property  # noqa: PLC0415
        from world.mechanics.services import stage_property  # noqa: PLC0415

        account = resolve_account_or_none(actor)
        if not _account_can_gm_room(actor, account):
            return ActionResult(success=False, message=_MSG_GM_ONLY)

        property_name = kwargs.get("property")
        if not property_name:
            return ActionResult(success=False, message=_MSG_NO_PROPERTY)
        try:
            property_obj = resolve_model_by_pk_or_name(
                Property,
                str(property_name),
                not_found_msg=f"No property named {property_name!r}.",
            )
        except CommandError as exc:
            return ActionResult(success=False, message=str(exc))

        target = _resolve_target_obj(actor, kwargs)
        if target is None:
            return ActionResult(success=False, message=_MSG_NO_ROOM)

        value = kwargs.get("value") or 1
        stage_property(target, property_obj, int(value))
        return ActionResult(
            success=True,
            message=f"{target.db_key} is now {property_obj.name}.",
            data={"object_id": target.pk, "property_id": property_obj.pk},
        )
