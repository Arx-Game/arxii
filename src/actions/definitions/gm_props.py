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
from world.magic.types.substance import MarkOutcome

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from world.magic.models import KindledStrengthTier

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

        try:
            pk = int(target_id)
        except (TypeError, ValueError):
            return None
        return _ObjectDB.objects.filter(pk=pk, db_location=actor.location).first()
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


_MSG_GM_ONLY_SUBSTANCE = "Only the scene's GM, owner, or staff may mark what is present here."
_MSG_NO_SCENE = "No scene is running here."
_MSG_NO_SUBSTANCE = "Which substance? Name one staff gave a gift (for example: shadow)."

_MARK_REPLIES = {
    MarkOutcome.MARKED: "{Label} is now present here for this scene.",
    MarkOutcome.ALREADY: "{Label} is already present here.",
    MarkOutcome.REMOVED: "The mark on {label} is removed.",
    MarkOutcome.HELD_FIXED: "This place is held fixed; {label} cannot be marked here.",
    MarkOutcome.NO_PLACE: "This place cannot hold a mark.",
}


def _resolve_substance(value: object):
    """A ``GiftSubstance`` by its gift's pk or by its label (case-insensitive), or None."""
    from world.magic.models import GiftSubstance  # noqa: PLC0415

    if value in (None, ""):
        return None
    text = str(value).strip()
    if text.isdigit():
        return GiftSubstance.objects.filter(gift_id=int(text)).select_related("gift").first()
    return (
        GiftSubstance.objects.filter(label__iexact=text)
        .select_related("gift")
        .order_by("gift_id")
        .first()
    )


@dataclass
class MarkSubstancePresentAction(Action):
    """GM improv (#5018): "is there shadow here?" "Yes." Marks it present for the scene.

    The mark is a room-reading row (``scene_mark:<scene>:<gift>``) set to just what makes
    the substance present, and it clears when the scene ends, however it ends. No room
    line: the GM's own words are the answer.
    """

    key: str = "stage_substance"
    name: str = "Mark Present Here"
    icon: str = "sparkles"
    category: str = "items"
    target_type: TargetType = TargetType.SELF

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from actions.kwarg_parsing import truthy_kwarg  # noqa: PLC0415
        from world.magic.services.substance import mark_substance_present  # noqa: PLC0415
        from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

        account = resolve_account_or_none(actor)
        if not _account_can_gm_room(actor, account):
            return ActionResult(success=False, message=_MSG_GM_ONLY_SUBSTANCE)
        room = actor.location
        scene = get_active_scene(room) if room is not None else None
        if scene is None:
            return ActionResult(success=False, message=_MSG_NO_SCENE)
        substance = _resolve_substance(kwargs.get("substance"))
        if substance is None:
            return ActionResult(success=False, message=_MSG_NO_SUBSTANCE)
        present = truthy_kwarg(kwargs.get("present", True))
        outcome = mark_substance_present(
            scene=scene, substance=substance, room=room, present=present
        )
        message = _MARK_REPLIES[outcome].format(
            label=substance.label, Label=substance.label.capitalize()
        )
        return ActionResult(
            success=outcome in {MarkOutcome.MARKED, MarkOutcome.ALREADY, MarkOutcome.REMOVED},
            message=message,
            data={"gift_id": substance.gift_id, "outcome": outcome},
        )


@dataclass
class GMListSubstancesAction(Action):
    """The GM Stage tab's list (#5018): every substance staff gave a gift, and what this
    scene has marked present here."""

    key: str = "gm_list_substances"
    name: str = "List Substances"
    icon: str = "list"
    category: str = "items"
    target_type: TargetType = TargetType.SELF

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from world.magic.models import GiftSubstance  # noqa: PLC0415
        from world.magic.services.substance import scene_substance_marks  # noqa: PLC0415
        from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

        account = resolve_account_or_none(actor)
        if not _account_can_gm_room(actor, account):
            return ActionResult(success=False, message=_MSG_GM_ONLY_SUBSTANCE)
        scene = get_active_scene(actor.location) if actor.location is not None else None
        substances = [
            {"gift_id": row.gift_id, "label": row.label}
            for row in GiftSubstance.objects.order_by("label", "gift_id")
        ]
        marked = (
            [{"gift_id": row.gift_id, "label": row.label} for row in scene_substance_marks(scene)]
            if scene is not None
            else []
        )
        lines = [f"{row['label']}" for row in substances] or ["No gift has a substance yet."]
        return ActionResult(
            success=True,
            message="Substances: " + ", ".join(lines),
            data={"substances": substances, "marked": marked},
        )


_MSG_GM_ONLY_KINDLE = "Only the scene's GM, owner, or staff may kindle a resonance."
_MSG_NO_KINDLE_TARGET = "Whose resonance? Name a character here."
_MSG_NO_RESONANCE = "Which resonance? Name one they hold."
_MSG_NOT_HELD = "They do not hold that resonance."


def _resolve_kindle_tier(value: object) -> KindledStrengthTier | None:
    """A ``KindledStrengthTier`` by rank or by name (case-insensitive); the weakest when blank.

    Returns None when a value is given and no strength matches.
    """
    from world.magic.models import KindledStrengthTier  # noqa: PLC0415

    tiers = KindledStrengthTier.objects.order_by("rank")
    text = str(value).strip() if value not in (None, "") else ""
    if not text:
        return tiers.first()
    if text.isdigit():
        return tiers.filter(rank=int(text)).first()
    return tiers.filter(name__iexact=text).first()


@dataclass
class KindleResonanceAction(Action):
    """GM improv (#5124): "is her Fury kindled?" "Yes." Kindles it for the rest of the scene.

    Writes a GM ``Kindling`` for the character, resonance and the room's active scene at a
    strength the GM picks (a strength's name or its rank; the weakest when none is named).
    Kindling it again sets the new strength. It ends with the scene.
    """

    key: str = "stage_kindle"
    name: str = "Kindle Resonance"
    icon: str = "flame"
    category: str = "items"
    target_type: TargetType = TargetType.SINGLE
    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target"})

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
        from world.magic.models import Resonance  # noqa: PLC0415
        from world.magic.services.kindling import holds_resonance, kindle_by_gm  # noqa: PLC0415
        from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

        account = resolve_account_or_none(actor)
        if not _account_can_gm_room(actor, account):
            return ActionResult(success=False, message=_MSG_GM_ONLY_KINDLE)
        scene = get_active_scene(actor.location) if actor.location is not None else None
        if scene is None:
            return ActionResult(success=False, message=_MSG_NO_SCENE)
        target = _resolve_target_obj(actor, kwargs)
        sheet = CharacterSheet.objects.filter(pk=target.pk).first() if target else None
        if sheet is None or target is actor.location:
            return ActionResult(success=False, message=_MSG_NO_KINDLE_TARGET)
        name = kwargs.get("resonance")
        if not name:
            return ActionResult(success=False, message=_MSG_NO_RESONANCE)
        try:
            resonance = resolve_model_by_pk_or_name(
                Resonance, str(name), not_found_msg=f"No resonance named {name!r}."
            )
        except CommandError as exc:
            return ActionResult(success=False, message=str(exc))
        if not holds_resonance(sheet, resonance):
            return ActionResult(success=False, message=_MSG_NOT_HELD)
        tier = _resolve_kindle_tier(kwargs.get("strength"))
        if tier is None:
            return ActionResult(success=False, message="No such strength.")
        gm_sheet = CharacterSheet.objects.filter(pk=actor.pk).first()
        kindle_by_gm(sheet=sheet, resonance=resonance, tier=tier, scene=scene, gm=gm_sheet)
        return ActionResult(
            success=True,
            message=(
                f"{target.db_key}'s {resonance.name} is kindled, {tier.name.lower()}, "
                "for this scene."
            ),
            data={"resonance_id": resonance.pk, "strength": tier.rank},
        )


@dataclass
class GMListKindlingAction(Action):
    """The GM Stage tab's Kindle list (#5124): the strengths staff named, the resonances the
    chosen character holds, and what the GM has kindled for this scene."""

    key: str = "gm_list_kindling"
    name: str = "List Kindling"
    icon: str = "list"
    category: str = "items"
    target_type: TargetType = TargetType.SINGLE
    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target"})

    def execute(self, actor: ObjectDB, context: Any = None, **kwargs: Any) -> ActionResult:
        from world.magic.constants import KindlingSource  # noqa: PLC0415
        from world.magic.models import KindledStrengthTier, Kindling  # noqa: PLC0415
        from world.magic.services.kindling import held_resonance_names  # noqa: PLC0415
        from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

        account = resolve_account_or_none(actor)
        if not _account_can_gm_room(actor, account):
            return ActionResult(success=False, message=_MSG_GM_ONLY_KINDLE)
        scene = get_active_scene(actor.location) if actor.location is not None else None
        target = _resolve_target_obj(actor, kwargs)
        if target is None or target is actor.location:
            return ActionResult(success=False, message=_MSG_NO_KINDLE_TARGET)
        sheet_id = target.pk
        strengths = [
            {"rank": tier.rank, "name": tier.name}
            for tier in KindledStrengthTier.objects.order_by("rank")
        ]
        held = held_resonance_names([sheet_id]).get(sheet_id, [])
        kindled = (
            [
                {
                    "resonance_id": row.resonance_id,
                    "strength": row.strength,
                    "by_viewer": row.kindled_by_id == actor.pk,
                }
                for row in Kindling.objects.filter(
                    scene=scene, source=KindlingSource.GM, character_sheet_id=sheet_id
                )
            ]
            if scene is not None
            else []
        )
        return ActionResult(
            success=True,
            message="Strengths: " + ", ".join(row["name"] for row in strengths),
            data={
                "strengths": strengths,
                "resonances": [{"id": pk, "name": name} for pk, name in held],
                "kindled": kindled,
            },
        )
