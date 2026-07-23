"""Goal authoring actions — set allocations and log progress (#1350).

Thin REGISTRY Actions over the extracted ``world.goals.services`` write
functions; the web ViewSet and telnet ``CmdGoal`` converge on ``action.run()``
(ADR-0001).
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
class SetCharacterGoalsAction(Action):
    """Set (replace) a character's goal allocations (weekly revision gated)."""

    key: str = "set_character_goals"
    name: str = "Set Character Goals"
    icon: str = "target"
    category: str = "goals"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.goals.services import set_character_goals  # noqa: PLC0415
        from world.goals.types import GoalError  # noqa: PLC0415

        goals = kwargs.get("goals")
        if not goals:
            return ActionResult(success=False, message="No goals provided.")
        try:
            created = set_character_goals(character=actor.sheet_data, goals=goals)
        except GoalError as exc:
            return ActionResult(success=False, message=exc.user_message)

        total_points = sum(g.points for g in created)
        return ActionResult(
            success=True,
            message=f"Goals set — {total_points} points allocated across {len(created)} domains.",
            data={"goal_ids": [g.pk for g in created], "total_points": total_points},
        )


@dataclass
class LogGoalProgressAction(Action):
    """Log a journal entry about goal progress (awards 1 XP)."""

    key: str = "log_goal_progress"
    name: str = "Log Goal Progress"
    icon: str = "book-open"
    category: str = "goals"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.goals.services import log_goal_progress  # noqa: PLC0415

        title = kwargs.get("title")
        content = kwargs.get("content")
        if not title or not content:
            return ActionResult(success=False, message="A title and content are required.")
        journal = log_goal_progress(
            character=actor.sheet_data,
            domain=kwargs.get("domain"),
            title=title,
            content=content,
            is_public=bool(kwargs.get("is_public", False)),
        )
        return ActionResult(
            success=True,
            message=f"You log progress: {journal.title}.",
            data={"journal_id": journal.pk},
        )
