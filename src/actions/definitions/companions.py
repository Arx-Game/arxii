"""Bind Companion action (#672) — attempt to bind a wild beast as a companion."""

from __future__ import annotations

from dataclasses import dataclass

from actions.base import Action
from actions.constants import ActionCategory
from actions.prerequisites import HasCompanionCapacityPrerequisite, Prerequisite
from actions.types import ActionResult, TargetType


def _resolve_owned_companion(actor, companion_id: int):
    """Fetch a companion, validating it belongs to the actor and is active.

    Returns ``(companion, None)`` on success, or ``(None, ActionResult)``
    with a failure result explaining why the companion can't be used.
    """
    from world.companions.models import Companion  # noqa: PLC0415

    try:
        companion = Companion.objects.select_related("archetype", "owner").get(
            pk=companion_id,
        )
    except Companion.DoesNotExist:
        return None, ActionResult(success=False, message="No such companion.")

    if not companion.is_active:
        return None, ActionResult(success=False, message=f"{companion.name} is no longer active.")
    if companion.owner != actor.sheet_data:
        return None, ActionResult(success=False, message="That is not your companion.")
    if companion.objectdb is None:
        return None, ActionResult(
            success=False, message=f"{companion.name} has no in-world presence."
        )
    return companion, None


@dataclass
class BindCompanionAction(Action):
    key: str = "bind_companion"
    name: str = "Bind Companion"
    icon: str = "paw"
    category: str = "companions"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HasCompanionCapacityPrerequisite()]

    def execute(self, actor, context=None, **kwargs) -> ActionResult:
        from world.checks.models import CheckType  # noqa: PLC0415
        from world.checks.services import perform_check  # noqa: PLC0415
        from world.companions.content import BIND_ATTEMPT_CHECK_NAME  # noqa: PLC0415
        from world.companions.models import CompanionArchetype  # noqa: PLC0415
        from world.companions.services import bind_companion  # noqa: PLC0415
        from world.magic.models.gifts import Gift  # noqa: PLC0415

        gift_id = kwargs.get("gift_id")
        archetype_id = kwargs.get("archetype_id")
        name = kwargs.get("name")
        if not gift_id or not archetype_id or not name:
            return ActionResult(success=False, message="Pick a gift, an archetype, and a name.")

        gift = Gift.objects.get(pk=gift_id)
        archetype = CompanionArchetype.objects.get(pk=archetype_id)
        sheet = actor.sheet_data
        check_type = CheckType.objects.get(name=BIND_ATTEMPT_CHECK_NAME)

        result = perform_check(actor, check_type, target_difficulty=archetype.bind_difficulty)
        if result.outcome is None or result.outcome.success_level < 0:
            return ActionResult(
                success=False,
                message=f"The {archetype.name} resists your attempt to bind it.",
            )

        companion = bind_companion(owner=sheet, archetype=archetype, granting_gift=gift, name=name)
        return ActionResult(
            success=True,
            message=f"{name} the {archetype.name} is now bonded to you.",
            data={"companion_id": companion.pk},
        )


@dataclass
class CompanionFightAction(Action):
    """Commit a bonded companion into a duel-scale encounter (#1873)."""

    key: str = "companion_fight"
    name: str = "Companion Fight"
    icon: str = "sword"
    category: str = "companions"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def execute(self, actor, context=None, **kwargs) -> ActionResult:
        from world.combat.constants import ParticipantStatus  # noqa: PLC0415
        from world.combat.models import CombatParticipant  # noqa: PLC0415
        from world.companions.services import (  # noqa: PLC0415
            materialize_companion_as_combat_opponent,
        )

        companion_id = kwargs.get("companion_id")
        if not companion_id:
            return ActionResult(success=False, message="Pick a companion to commit.")

        companion, failure = _resolve_owned_companion(actor, companion_id)
        if failure is not None:
            return failure

        participant = (
            CombatParticipant.objects.filter(
                character_sheet=actor.sheet_data,
                status=ParticipantStatus.ACTIVE,
            )
            .select_related("encounter")
            .first()
        )
        if participant is None:
            return ActionResult(success=False, message="You are not in active combat.")

        opponent = materialize_companion_as_combat_opponent(companion, participant.encounter)
        return ActionResult(
            success=True,
            message=f"{companion.name} joins the fight!",
            data={"opponent_id": opponent.pk},
        )


@dataclass
class DeployCompanionAction(Action):
    """Deploy a bonded companion into a battle-scale BattleVehicle (#1873)."""

    key: str = "deploy_companion"
    name: str = "Deploy Companion"
    icon: str = "flag"
    category: str = "companions"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def execute(self, actor, context=None, **kwargs) -> ActionResult:
        from world.battles.constants import BattleParticipantStatus  # noqa: PLC0415
        from world.battles.models import BattleParticipant  # noqa: PLC0415
        from world.companions.services import (  # noqa: PLC0415
            materialize_companion_as_battle_vehicle,
        )

        companion_id = kwargs.get("companion_id")
        if not companion_id:
            return ActionResult(success=False, message="Pick a companion to deploy.")

        companion, failure = _resolve_owned_companion(actor, companion_id)
        if failure is not None:
            return failure

        battle_participant = (
            BattleParticipant.objects.filter(
                character_sheet=actor.sheet_data,
                status=BattleParticipantStatus.ACTIVE,
            )
            .select_related("battle", "side")
            .first()
        )
        if battle_participant is None:
            return ActionResult(success=False, message="You are not in a battle.")

        vehicle = materialize_companion_as_battle_vehicle(
            companion,
            battle_participant.battle,
            battle_participant.side,
        )
        return ActionResult(
            success=True,
            message=f"{companion.name} is deployed into the battle!",
            data={"vehicle_id": vehicle.pk},
        )
