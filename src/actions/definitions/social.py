"""Social action stubs -- contested social actions for scene checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionContext, ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


@dataclass
class IntimidateAction(Action):
    """Attempt to intimidate a target through force of presence."""

    key: str = "intimidate"
    name: str = "Intimidate"
    icon: str = "skull"
    category: str = "social"
    target_type: TargetType = TargetType.SINGLE

    intent_event: str | None = "before_intimidate"
    result_event: str | None = "intimidate"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        return ActionResult(success=True, message="Intimidation attempted.")


@dataclass
class PersuadeAction(Action):
    """Attempt to persuade a target through reasoned argument."""

    key: str = "persuade"
    name: str = "Persuade"
    icon: str = "handshake"
    category: str = "social"
    target_type: TargetType = TargetType.SINGLE

    intent_event: str | None = "before_persuade"
    result_event: str | None = "persuade"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        return ActionResult(success=True, message="Persuasion attempted.")


@dataclass
class DeceiveAction(Action):
    """Attempt to deceive a target through misdirection or lies."""

    key: str = "deceive"
    name: str = "Deceive"
    icon: str = "mask"
    category: str = "social"
    target_type: TargetType = TargetType.SINGLE

    intent_event: str | None = "before_deceive"
    result_event: str | None = "deceive"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        return ActionResult(success=True, message="Deception attempted.")


@dataclass
class FlirtAction(Action):
    """Attempt to charm or seduce a target."""

    key: str = "flirt"
    name: str = "Flirt"
    icon: str = "heart"
    category: str = "social"
    target_type: TargetType = TargetType.SINGLE

    intent_event: str | None = "before_flirt"
    result_event: str | None = "flirt"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        return ActionResult(success=True, message="Flirtation attempted.")


@dataclass
class PerformAction(Action):
    """Perform for an audience -- music, oration, storytelling."""

    key: str = "perform"
    name: str = "Perform"
    icon: str = "music"
    category: str = "social"
    target_type: TargetType = TargetType.AREA

    intent_event: str | None = "before_perform"
    result_event: str | None = "perform"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        return ActionResult(success=True, message="Performance attempted.")


@dataclass
class EntranceAction(Action):
    """Attempt to captivate all observers through sheer presence."""

    key: str = "entrance"
    name: str = "Entrance"
    icon: str = "sparkles"
    category: str = "social"
    target_type: TargetType = TargetType.AREA

    intent_event: str | None = "before_entrance"
    result_event: str | None = "entrance"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        return ActionResult(success=True, message="Entrance attempted.")
