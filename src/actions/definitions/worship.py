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
