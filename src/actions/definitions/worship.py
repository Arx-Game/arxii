"""Worship actions (#3777): performing a being's rite in a live scene."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from evennia.objects.models import ObjectDB

from actions.base import Action, ActionResult
from actions.types import ActionContext, TargetType


def _resolve_rite(kwargs: dict[str, Any]):
    """(rite, error): a ``rite`` object wins; else ``rite_name`` (+ ``being_name``)."""
    from world.worship.models import WorshipRite  # noqa: PLC0415

    rite = kwargs.get("rite")
    if rite is not None:
        return rite, None
    name = (kwargs.get("rite_name") or "").strip()
    if not name:
        return None, ActionResult(success=False, message="Perform which rite?")
    rites = WorshipRite.objects.filter(name__iexact=name, is_active=True, being__is_active=True)
    being_name = (kwargs.get("being_name") or "").strip()
    if being_name:
        rites = rites.filter(being__name__iexact=being_name)
    rites = list(rites.select_related("being", "kind")[:2])
    if not rites:
        return None, ActionResult(success=False, message="No such rite.")
    if len(rites) > 1:
        return None, ActionResult(
            success=False, message="More than one being has a rite by that name; name the being."
        )
    return rites[0], None


@dataclass
class PerformWorshipRiteAction(Action):
    """Perform one of a being's rites in the scene you stand in (#3777).

    kwargs:
        rite: A ``WorshipRite`` (required unless ``rite_name`` is given).
        rite_name: The rite's name; ``being_name`` narrows it when two beings
            share one.
    """

    key: str = "worship_rite"
    name: str = "Perform Rite"
    icon: str = "flame"
    category: str = "worship"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415
        from world.worship.exceptions import WorshipRiteError  # noqa: PLC0415
        from world.worship.rite_services import perform_worship_rite  # noqa: PLC0415

        rite, error = _resolve_rite(kwargs)
        if error is not None:
            return error
        try:
            sheet = actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            sheet = None
        if sheet is None:
            return ActionResult(
                success=False, message="You have no character sheet to worship with."
            )
        scene = get_active_scene(actor.location)
        if scene is None:
            return ActionResult(success=False, message="A rite is performed in a live scene.")
        try:
            outcome = perform_worship_rite(sheet, rite, scene=scene)
        except WorshipRiteError as exc:
            return ActionResult(success=False, message=exc.user_message)
        parts = [
            f"You perform {rite.name} in the name of {rite.being.name}: {outcome.outcome_name}."
        ]
        if outcome.resonance_granted:
            parts.append(f"+{outcome.resonance_granted} {rite.resonance.resonance.name} resonance.")
        if outcome.favor_granted:
            parts.append(f"+{outcome.favor_granted} favor with {rite.being.name}.")
        elif outcome.favor_capped:
            parts.append(f"{rite.being.name} has already marked this rite of yours this week.")
        return ActionResult(
            success=True,
            message=" ".join(parts),
            data={
                "outcome": outcome.outcome_name,
                "resonance_granted": outcome.resonance_granted,
                "favor_granted": outcome.favor_granted,
                "favor_capped": outcome.favor_capped,
            },
        )


def _resolve_being(kwargs: dict[str, Any]):
    from world.worship.models import WorshippedBeing  # noqa: PLC0415

    being = kwargs.get("being")
    if being is not None:
        return being, None
    name = (kwargs.get("being_name") or "").strip()
    if not name:
        return None, ActionResult(success=False, message="Name the being.")
    being = WorshippedBeing.objects.filter(name__iexact=name, is_active=True).first()
    if being is None:
        return None, ActionResult(success=False, message=f"No being '{name}' is known.")
    return being, None


def _actor_persona_and_room(actor: ObjectDB):
    """(persona, room_profile, error) for the room the actor stands in."""
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    try:
        sheet = actor.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        sheet = None
    if sheet is None:
        return None, None, ActionResult(success=False, message="You have no character sheet.")
    try:
        persona = active_persona_for_sheet(sheet)
    except ObjectDoesNotExist:
        persona = None
    if persona is None:
        return None, None, ActionResult(success=False, message="You have no persona to act as.")
    location = actor.location
    profile = location.room_profile_or_none if location is not None else None
    if profile is None:
        return (
            None,
            None,
            ActionResult(success=False, message="This place has no room to consecrate."),
        )
    return persona, profile, None


@dataclass
class FoundShrineAction(Action):
    """Found a shrine of a being in a room you own (#3778). kwargs: ``being`` or ``being_name``."""

    key: str = "shrine_found"
    name: str = "Found Shrine"
    icon: str = "candle"
    category: str = "worship"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.worship.consecration_services import found_shrine  # noqa: PLC0415
        from world.worship.exceptions import ConsecrationError  # noqa: PLC0415

        persona, profile, error = _actor_persona_and_room(actor)
        if error is not None:
            return error
        being, error = _resolve_being(kwargs)
        if error is not None:
            return error
        try:
            found_shrine(profile, being, persona)
        except ConsecrationError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, message=f"You found a shrine of {being.name} here.")


@dataclass
class DissolveShrineAction(Action):
    """Dissolve the shrine in the room you stand in (#3778): its founder or the room's holder."""

    key: str = "shrine_dissolve"
    name: str = "Dissolve Shrine"
    icon: str = "candle-off"
    category: str = "worship"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.worship.consecration_services import dissolve_shrine, shrine_at  # noqa: PLC0415
        from world.worship.exceptions import ConsecrationError  # noqa: PLC0415

        persona, profile, error = _actor_persona_and_room(actor)
        if error is not None:
            return error
        shrine = shrine_at(profile)
        if shrine is None:
            return ActionResult(success=False, message="There is no shrine here.")
        try:
            dissolve_shrine(shrine, persona)
        except ConsecrationError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True, message=f"The shrine of {shrine.being.name} is dissolved."
        )


@dataclass
class DedicateTempleAction(Action):
    """Dedicate the building you stand in to a being (#3778): ``being`` or ``being_name``."""

    key: str = "temple_dedicate"
    name: str = "Dedicate Temple"
    icon: str = "church"
    category: str = "worship"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.worship.consecration_services import (  # noqa: PLC0415
            building_over,
            dedicate_temple,
        )
        from world.worship.exceptions import ConsecrationError  # noqa: PLC0415

        persona, profile, error = _actor_persona_and_room(actor)
        if error is not None:
            return error
        building = building_over(profile)
        if building is None:
            return ActionResult(success=False, message="This room is not inside a building.")
        being, error = _resolve_being(kwargs)
        if error is not None:
            return error
        try:
            dedicate_temple(building, being, persona)
        except ConsecrationError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True, message=f"You dedicate {building.area.name} as a temple of {being.name}."
        )


@dataclass
class RevokeTempleAction(Action):
    """Revoke the temple dedication of the building you stand in (#3778)."""

    key: str = "temple_revoke"
    name: str = "Revoke Temple"
    icon: str = "church-off"
    category: str = "worship"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.worship.consecration_services import revoke_temple, temple_over  # noqa: PLC0415
        from world.worship.exceptions import ConsecrationError  # noqa: PLC0415

        persona, profile, error = _actor_persona_and_room(actor)
        if error is not None:
            return error
        dedication = temple_over(profile)
        if dedication is None:
            return ActionResult(success=False, message="This building is not a temple.")
        try:
            revoke_temple(dedication, persona)
        except ConsecrationError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True, message=f"The temple of {dedication.being.name} is no longer dedicated."
        )
