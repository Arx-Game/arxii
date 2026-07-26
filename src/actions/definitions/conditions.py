"""Condition-related player actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.constants import ActionCategory, TargetKind
from actions.types import ActionContext, ActionResult, TargetFilters, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


@dataclass
class TreatConditionAction(Action):
    """Offer to treat another character's condition or pending alteration."""

    key: str = "treat_condition"
    name: str = "Treat Condition"
    icon: str = "heart-pulse"
    category: str = "condition"
    target_type: TargetType = TargetType.SINGLE
    target_kind: TargetKind | None = TargetKind.PERSONA
    target_filters: TargetFilters | None = None
    action_category: ActionCategory | None = ActionCategory.SOCIAL
    costs_turn: bool = True

    def __post_init__(self) -> None:
        self.target_filters = TargetFilters(in_same_scene=True, exclude_self=True)

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        """Direct execution path is not used by the consent flow.

        The telnet/web surfaces create a SceneActionRequest via
        create_action_request. If something calls run() directly, fail clearly.
        """
        return ActionResult(
            success=False,
            message="Use the scene treatment request flow to treat another character.",
        )


treat_condition = TreatConditionAction()


@dataclass
class BreakFreeAction(Action):
    """Attempt to break free from a behavior-altering condition (#2706)."""

    key: str = "break_free"
    name: str = "Break Free"
    icon: str = "shield-off"
    category: str = "condition"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.conditions.models import ConditionInstance  # noqa: PLC0415
        from world.conditions.services import attempt_break_free  # noqa: PLC0415

        condition_name = kwargs.get("condition_name")

        instances = (
            ConditionInstance.objects.select_related("condition", "condition__category")
            .filter(
                target=actor,
                resolved_at__isnull=True,
                condition__category__alters_behavior=True,
            )
            .exclude(condition__break_free_mode="none")
        )
        if condition_name:
            instances = instances.filter(condition__name__iexact=condition_name)

        if not instances.exists():
            return ActionResult(
                success=False,
                message="You have nothing you can fight off.",
            )

        instance = max(
            instances,
            key=lambda i: (i.severity, i.condition.break_free_difficulty),
        )

        result = attempt_break_free(instance, in_combat_tick=False)
        return ActionResult(
            success=result.broke_free or result.attempted,
            message=result.message,
        )


break_free = BreakFreeAction()


@dataclass
class RevealConditionAction(Action):
    """Reveal a subtle behavior-altering condition to an unaware target (#2706)."""

    key: str = "reveal_condition"
    name: str = "Reveal Condition"
    icon: str = "eye"
    category: str = "condition"
    target_type: TargetType = TargetType.SINGLE
    target_kind: TargetKind | None = TargetKind.PERSONA
    action_category: ActionCategory | None = ActionCategory.SOCIAL

    def __post_init__(self) -> None:
        self.target_filters = TargetFilters(in_same_scene=True, exclude_self=True)

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.checks.services import level_opposition, perform_check  # noqa: PLC0415
        from world.conditions.models import ConditionInstance  # noqa: PLC0415
        from world.progression.services.skill_development import (  # noqa: PLC0415
            get_character_path_level,
        )

        target = kwargs.get("target")
        if target is None:
            return ActionResult(success=False, message="You must specify a target.")

        instances = ConditionInstance.objects.select_related(
            "condition", "condition__category"
        ).filter(
            target=target,
            resolved_at__isnull=True,
            is_aware=False,
            condition__category__alters_behavior=True,
        )
        if not instances.exists():
            return ActionResult(
                success=False,
                message="You don't notice anything amiss with them.",
            )

        instance = instances.first()
        template = instance.condition

        check_type = template.break_free_check_type or template.resist_check_type
        if check_type is None:
            return ActionResult(success=False, message="Cannot determine how to detect this.")

        difficulty = template.subtlety
        caster = instance.source_character
        if caster is not None:
            caster_level = get_character_path_level(caster)
            difficulty += level_opposition(check_type, level=caster_level, character=caster)

        result = perform_check(actor, check_type, target_difficulty=difficulty)
        if result.success_level > 0:
            instance.is_aware = True
            instance.save(update_fields=["is_aware"])
            return ActionResult(
                success=True,
                message=f"You sense that {target.key} is under the influence of {template.name}!",
            )
        return ActionResult(success=False, message="You can't quite put your finger on it.")


reveal_condition = RevealConditionAction()


@dataclass
class RallyAction(Action):
    """Rally an afflicted character to fight off a behavior-altering condition (#2706)."""

    key: str = "rally"
    name: str = "Rally"
    icon: str = "megaphone"
    category: str = "condition"
    target_type: TargetType = TargetType.SINGLE
    target_kind: TargetKind | None = TargetKind.PERSONA
    action_category: ActionCategory | None = ActionCategory.SOCIAL

    def __post_init__(self) -> None:
        self.target_filters = TargetFilters(in_same_scene=True, exclude_self=True)

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.checks.services import level_opposition, perform_check  # noqa: PLC0415
        from world.conditions.services import attempt_break_free  # noqa: PLC0415
        from world.progression.services.skill_development import (  # noqa: PLC0415
            get_character_path_level,
        )

        target = kwargs.get("target")
        if target is None:
            return ActionResult(success=False, message="You must specify a target.")

        from world.conditions.models import ConditionInstance  # noqa: PLC0415

        instances = (
            ConditionInstance.objects.select_related("condition", "condition__category")
            .filter(
                target=target,
                resolved_at__isnull=True,
                is_aware=True,
                condition__category__alters_behavior=True,
            )
            .exclude(condition__break_free_mode="none")
        )
        if not instances.exists():
            return ActionResult(
                success=False,
                message="They don't seem to be fighting anything.",
            )

        instance = max(
            instances,
            key=lambda i: (i.severity, i.condition.break_free_difficulty),
        )

        check_type = (
            instance.condition.break_free_check_type or instance.condition.resist_check_type
        )
        if check_type is None:
            return ActionResult(success=False, message="Cannot determine how to rally them.")

        difficulty = instance.condition.break_free_difficulty
        caster = instance.source_character
        if caster is not None:
            caster_level = get_character_path_level(caster)
            difficulty += level_opposition(check_type, level=caster_level, character=caster)

        result = perform_check(actor, check_type, target_difficulty=difficulty)
        sl = result.success_level

        crit_threshold = 2
        if sl >= crit_threshold:
            break_result = attempt_break_free(
                instance,
                helper_bonus=sl * 5,
                in_combat_tick=True,
            )
            return ActionResult(
                success=True,
                message=f"Your voice cuts through! {break_result.message}",
            )
        if sl > 0:
            bonus = sl * 5
            instance.pending_rally_bonus = bonus
            instance.save(update_fields=["pending_rally_bonus"])
            return ActionResult(
                success=True,
                message=(
                    f"You rally {target.key}, granting them +{bonus}"
                    " to their next attempt to break free."
                ),
            )
        return ActionResult(success=False, message="Your words don't seem to reach them.")


rally = RallyAction()
