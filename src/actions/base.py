"""Base Action class — self-contained unit owning prerequisites, execution, and events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.prerequisites import Prerequisite
from actions.types import ActionAvailability, ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


@dataclass
class Action:
    """A self-contained action definition.

    Actions own their full lifecycle: prerequisites, intent event emission,
    execution, and result event emission. Commands (telnet) and the web
    dispatcher both call ``action.run()`` — the action handles everything.

    Subclasses override ``get_prerequisites()`` and ``execute()`` to define
    what the action checks and does.

    Attributes:
        key: Unique identifier for registry lookup (e.g., "look", "get").
        name: Human-readable name for UI display.
        icon: Icon identifier for frontend context menus.
        category: Grouping category (e.g., "perception", "combat").
        target_type: What kind of target this action operates on.
        intent_event: Event name emitted before execution (e.g., "before_look").
        result_event: Event name emitted after execution (e.g., "look").
    """

    key: str
    name: str
    icon: str
    category: str
    target_type: TargetType

    intent_event: str | None = None
    result_event: str | None = None

    def get_prerequisites(self) -> list[Prerequisite]:
        """Return the prerequisites that must be met for this action.

        Override in subclasses to define action-specific requirements.
        """
        return []

    def execute(self, actor: ObjectDB, **kwargs: Any) -> ActionResult:
        """Perform the action's core logic.

        Override in subclasses. Called after prerequisites pass and the
        intent event is not interrupted.

        Args:
            actor: The character performing the action.
            **kwargs: Action-specific parameters (target, text, etc.).

        Returns:
            Structured result of the action.
        """
        raise NotImplementedError

    def check_availability(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict[str, Any] | None = None,
    ) -> ActionAvailability:
        """Evaluate all prerequisites. Return availability with reasons.

        Args:
            actor: The character who would perform the action.
            target: Optional target of the action.
            context: Optional situational context (combat, scene, etc.).
        """
        failures = []
        for prereq in self.get_prerequisites():
            met, reason = prereq.is_met(actor, target, context)
            if not met:
                failures.append(reason)
        return ActionAvailability(
            action_key=self.key,
            available=len(failures) == 0,
            reasons=failures,
        )

    def run(self, actor: ObjectDB, **kwargs: Any) -> ActionResult:
        """Full lifecycle: intent event -> execute -> result event.

        This is the primary entry point. Both commands (telnet) and the
        web action dispatcher call this method.

        Args:
            actor: The character performing the action.
            **kwargs: Action-specific parameters (target, text, etc.).

        Returns:
            Structured result of the action.
        """
        # TODO: emit intent event and check for trigger interruption
        # TODO: collect and apply involuntary enhancement modifiers
        # TODO: emit result event for trigger reactions
        return self.execute(actor, **kwargs)
