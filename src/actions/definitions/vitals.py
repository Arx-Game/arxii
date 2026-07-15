"""Vitals lifecycle actions: waking from unconsciousness (#2287).

The retire and death-kudos actions from the same issue also live here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext


@dataclass
class RetireCharacterAction(Action):
    """Lay a dead character to rest: the final, player-fired release (#2287).

    Self-retire requires the actor to be dead ("well, time to shuffle off").
    Staff may pass ``target_name`` to force-retire another dead character
    (offscreen deaths). Auto-retire after the grace window is the
    ``vitals.auto_retire`` scheduler task, not this action.
    """

    key: str = "retire"
    name: str = "Retire"
    icon: str = "candle"
    category: str = "vitals"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.vitals.services import retire_character  # noqa: PLC0415

        target_name = kwargs.get("target_name")
        if target_name:
            return self._force_retire(actor, target_name)

        try:
            sheet = actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            sheet = None
        if sheet is None:
            return ActionResult(success=False, message="You have no character sheet.")
        try:
            retire_character(sheet)
        except ValueError:
            return ActionResult(success=False, message="Only the dead may shuffle off.")
        return ActionResult(
            success=True,
            message="You let go. This character is at rest; thank you for their story.",
        )

    @staticmethod
    def _force_retire(actor: ObjectDB, target_name: str) -> ActionResult:
        """Staff force path: retire another dead character (offscreen deaths)."""
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from core_management.permissions import is_staff_observer  # noqa: PLC0415
        from world.vitals.services import retire_character  # noqa: PLC0415

        if not is_staff_observer(actor):
            return ActionResult(success=False, message="Only staff may retire another character.")
        found = actor.search(target_name, global_search=True, quiet=True)
        target = found[0] if found else None
        if target is None:
            return ActionResult(success=False, message=f"No character '{target_name}' found.")
        try:
            sheet = target.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            return ActionResult(success=False, message="That is not a character.")
        try:
            retire_character(sheet, forced_by=actor.db_account)
        except ValueError as exc:
            return ActionResult(success=False, message=str(exc))
        return ActionResult(success=True, message=f"{target.key} has been laid to rest.")


@dataclass
class GiveDeathKudosAction(Action):
    """Honor how a player handled their character's death (#2287).

    Wraps ``world.vitals.death_kudos.award_death_kudos`` — eligibility
    (death-scene participant / GM / staff), tier amounts, the lifetime-XP
    cap, and the retire-closed window all live in the service.
    """

    key: str = "death_kudos"
    name: str = "Honor a Death"
    icon: str = "wreath"
    category: str = "vitals"
    target_type: TargetType = TargetType.SINGLE

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from evennia.objects.models import ObjectDB as ObjectDBModel  # noqa: PLC0415

        from world.vitals.death_kudos import DeathKudosError, award_death_kudos  # noqa: PLC0415

        target = kwargs.get("target")
        if isinstance(target, int):
            target = ObjectDBModel.objects.filter(pk=target).first()
        if target is None:
            target_name = kwargs.get("target_name")
            if target_name:
                found = actor.search(target_name, global_search=True, quiet=True)
                target = found[0] if found else None
        if target is None:
            return ActionResult(success=False, message="Honor whose death?")
        account = actor.db_account
        if account is None:
            return ActionResult(success=False, message="Only players may give death kudos.")
        try:
            result = award_death_kudos(account, target)
        except DeathKudosError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, message=result.message)


@dataclass
class WakeAction(Action):
    """Attempt to wake from Sleeping or Unconscious (#2287, #2290).

    For Sleeping (voluntary sleep): removes the condition immediately unless
    the character is dream-engaged (an active scene round in the dream room).

    For Unconscious (KO): runs the existing roll-based wake arc from #2287.
    """

    key: str = "wake"
    name: str = "Wake"
    icon: str = "sunrise"
    category: str = "vitals"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.conditions.models import ConditionTemplate  # noqa: PLC0415
        from world.conditions.services import (  # noqa: PLC0415
            has_condition,
            remove_condition,
        )
        from world.vitals.constants import SLEEPING_CONDITION_NAME  # noqa: PLC0415
        from world.vitals.services import attempt_wake  # noqa: PLC0415

        try:
            sheet = actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            sheet = None
        if sheet is None:
            return ActionResult(success=False, message="You are already awake.")

        # Check Sleeping first (voluntary sleep, #2290)
        sleeping_template = ConditionTemplate.objects.filter(
            name=SLEEPING_CONDITION_NAME,
        ).first()
        if sleeping_template is not None and has_condition(actor, sleeping_template):
            # Check dream engagement gate
            from world.dreams.engagement import is_dream_engaged  # noqa: PLC0415

            if is_dream_engaged(sheet):
                return ActionResult(
                    success=False,
                    message="You are lost in the dream; you cannot wake until the danger passes.",
                )
            # Check for escape lever — dreamwalk destination stored on the character's ndb
            destination = getattr(actor.ndb, "dreamwalk_destination", None)  # noqa: GETATTR_LITERAL

            remove_condition(actor, sleeping_template)

            # Escape lever: move to the dreamwalk destination if one was stored
            if destination is not None:
                actor.location = destination
                actor.save(update_fields=["db_location"])
                return ActionResult(
                    success=True,
                    message=(
                        "You wake — but not where you fell asleep."
                        " The dream has carried you elsewhere."
                    ),
                )
            return ActionResult(success=True, message="You wake from your dream.")

        # Fall through to Unconscious wake arc (#2287)
        result = attempt_wake(sheet)
        return ActionResult(success=result.woke, message=result.message)
