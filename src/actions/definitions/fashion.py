"""Fashion presentation actions: present_outfit, judge_presentation (#514)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionContext, ActionResult, TargetType
from flows.constants import EventName
from flows.scene_data_manager import SceneDataManager
from flows.service_functions.communication import message_location
from world.events.models import Event
from world.items.exceptions import FashionPresentationError
from world.items.models import FashionPresentation, Outfit
from world.items.services.fashion_presentation import (
    judge_presentation as judge_presentation_service,
    present_outfit as present_outfit_service,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


@dataclass
class PresentOutfitAction(Action):
    """Present an outfit at an event hosted by a society.

    The host society's current fashion-style taste shapes the check difficulty.
    The graded outcome sets the presentation's base_score (and initial acclaim).
    An optional outfit FK is recorded for bookkeeping; the check reads
    equipped items, not that FK.
    """

    key: str = "present_outfit"
    name: str = "Present Outfit"
    icon: str = "runway"
    category: str = "items"
    target_type: TargetType = TargetType.SINGLE

    intent_event: str | None = EventName.BEFORE_PRESENT_OUTFIT.value
    result_event: str | None = EventName.PRESENT_OUTFIT.value

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        event_id = kwargs.get("event_id")
        if event_id is None:
            return ActionResult(success=False, message="Present at which event?")
        try:
            event = Event.objects.get(pk=event_id)
        except Event.DoesNotExist:
            return ActionResult(success=False, message="That event no longer exists.")

        outfit_id = kwargs.get("outfit_id")
        outfit: Outfit | None = None
        if outfit_id is not None:
            try:
                outfit = Outfit.objects.get(pk=outfit_id)
            except Outfit.DoesNotExist:
                return ActionResult(success=False, message="That outfit no longer exists.")

        presenter = actor.sheet_data

        try:
            present_outfit_service(presenter, event, outfit)
        except FashionPresentationError as exc:
            return ActionResult(success=False, message=exc.user_message)

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        message_location(actor_state, "$You() $conj(present) your look.")
        return ActionResult(success=True)


@dataclass
class JudgePresentationAction(Action):
    """Endorse a peer's fashion presentation at an event.

    The judge must not be the presenter or an alt of the presenter.  Each
    judge may endorse a given presentation only once.  A successful endorsement
    recomputes the presentation's acclaim and rolls it into the presenter's
    primary persona's fashion prestige.
    """

    key: str = "judge_presentation"
    name: str = "Judge Presentation"
    icon: str = "gavel"
    category: str = "items"
    target_type: TargetType = TargetType.SINGLE

    intent_event: str | None = EventName.BEFORE_JUDGE_PRESENTATION.value
    result_event: str | None = EventName.JUDGE_PRESENTATION.value

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        presentation_id = kwargs.get("presentation_id")
        if presentation_id is None:
            return ActionResult(success=False, message="Judge which presentation?")
        try:
            presentation = FashionPresentation.objects.get(pk=presentation_id)
        except FashionPresentation.DoesNotExist:
            return ActionResult(success=False, message="That presentation no longer exists.")

        judge = actor.sheet_data

        try:
            endorsement = judge_presentation_service(judge, presentation)
        except FashionPresentationError as exc:
            return ActionResult(success=False, message=exc.user_message)

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        message_location(actor_state, "$You() $conj(nod) approvingly at the presentation.")
        return ActionResult(success=True, data={"endorsement": endorsement})
