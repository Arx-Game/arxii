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


@dataclass
class ReleaseCompanionAction(Action):
    """Release a bonded companion — destroy its live object, keep the row (#1918)."""

    key: str = "release_companion"
    name: str = "Release Companion"
    icon: str = "door-open"
    category: str = "companions"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def execute(self, actor, context=None, **kwargs) -> ActionResult:
        from world.companions.services import release_companion  # noqa: PLC0415

        companion_id = kwargs.get("companion_id")
        if not companion_id:
            return ActionResult(success=False, message="Pick a companion to release.")
        companion, failure = _resolve_owned_companion(actor, companion_id)
        if failure is not None:
            return failure
        name = companion.name
        release_companion(companion)
        return ActionResult(success=True, message=f"{name} is released from your bond.")


@dataclass
class MountCompanionAction(Action):
    """Mount a bonded, ridable companion (#1843)."""

    key: str = "mount_companion"
    name: str = "Mount"
    icon: str = "horse"
    category: str = "companions"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def execute(self, actor, context=None, **kwargs) -> ActionResult:
        from world.companions.services import MountError, mount_companion  # noqa: PLC0415

        companion_id = kwargs.get("companion_id")
        if not companion_id:
            return ActionResult(success=False, message="Mount which companion?")
        companion, failure = _resolve_owned_companion(actor, companion_id)
        if failure is not None:
            return failure
        try:
            mount_companion(actor.sheet_data, companion)
        except MountError as err:
            return ActionResult(success=False, message=err.user_message)
        return ActionResult(success=True, message=f"You mount {companion.name}.")


@dataclass
class DismountCompanionAction(Action):
    """Dismount from whichever companion the actor is currently riding (#1843)."""

    key: str = "dismount_companion"
    name: str = "Dismount"
    icon: str = "horse"
    category: str = "companions"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def execute(self, actor, context=None, **kwargs) -> ActionResult:
        from world.companions.services import MountError, dismount_companion  # noqa: PLC0415

        try:
            companion = dismount_companion(actor.sheet_data)
        except MountError as err:
            return ActionResult(success=False, message=err.user_message)
        return ActionResult(success=True, message=f"You dismount {companion.name}.")


@dataclass
class OrderCompanionAction(Action):
    """Direct a deployed companion in combat (#1921).

    A free directive — does not consume the player's round action or AP.
    The companion's NPC round-tick action is modified by the order.
    """

    key: str = "order_companion"
    name: str = "Order Companion"
    icon: str = "bullhorn"
    category: str = "companions"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def execute(self, actor, context=None, **kwargs) -> ActionResult:  # noqa: C901, PLR0911
        from world.combat.constants import ParticipantStatus  # noqa: PLC0415
        from world.combat.models import CombatOpponent, CombatParticipant  # noqa: PLC0415
        from world.companions.models import CompanionAbility  # noqa: PLC0415
        from world.companions.services import (  # noqa: PLC0415
            CompanionOrderError,
            order_companion,
        )

        companion_id = kwargs.get("companion_id")
        order_kind = kwargs.get("order_kind")
        if not companion_id or not order_kind:
            return ActionResult(success=False, message="Pick a companion and an order kind.")

        companion, failure = _resolve_owned_companion(actor, companion_id)
        if failure is not None:
            return failure

        target_id = kwargs.get("target_id")
        ability_id = kwargs.get("ability_id")
        ally_id = kwargs.get("ally_id")

        ability = None
        if ability_id:
            try:
                ability = CompanionAbility.objects.get(pk=ability_id)
            except CompanionAbility.DoesNotExist:
                return ActionResult(success=False, message="No such ability.")

        # Try duel-scale first
        participant = (
            CombatParticipant.objects.filter(
                character_sheet=actor.sheet_data,
                status=ParticipantStatus.ACTIVE,
            )
            .select_related("encounter")
            .first()
        )
        if participant is not None:
            target_opponent = None
            defending_participant = None
            if target_id:
                target_opponent = CombatOpponent.objects.filter(pk=target_id).first()
            if ally_id:
                defending_participant = CombatParticipant.objects.filter(pk=ally_id).first()

            try:
                order = order_companion(
                    companion=companion,
                    order_kind=order_kind,
                    encounter=participant.encounter,
                    round_number=participant.encounter.round_number,
                    target_opponent=target_opponent,
                    ability=ability,
                    defending_participant=defending_participant,
                )
            except CompanionOrderError as exc:
                return ActionResult(success=False, message=exc.user_message)
            return ActionResult(
                success=True,
                message=f"{companion.name} has been ordered to {order.get_order_kind_display()}.",
                data={"order_id": order.pk},
            )

        # Try battle-scale
        from world.battles.constants import BattleParticipantStatus  # noqa: PLC0415
        from world.battles.models import BattleParticipant, BattleUnit  # noqa: PLC0415

        battle_participant = (
            BattleParticipant.objects.filter(
                character_sheet=actor.sheet_data,
                status=BattleParticipantStatus.ACTIVE,
            )
            .select_related("battle")
            .first()
        )
        if battle_participant is not None:
            target_unit = None
            target_ally_bp = None
            if target_id:
                target_unit = BattleUnit.objects.filter(pk=target_id).first()
            if ally_id:
                target_ally_bp = BattleParticipant.objects.filter(pk=ally_id).first()

            battle_round = battle_participant.battle.current_round
            round_number = battle_round.round_number if battle_round else 1

            try:
                order = order_companion(
                    companion=companion,
                    order_kind=order_kind,
                    battle=battle_participant.battle,
                    round_number=round_number,
                    target_unit=target_unit,
                    ability=ability,
                    target_ally=target_ally_bp,
                )
            except CompanionOrderError as exc:
                return ActionResult(success=False, message=exc.user_message)
            return ActionResult(
                success=True,
                message=f"{companion.name} has been ordered to {order.get_order_kind_display()}.",
                data={"order_id": order.pk},
            )

        return ActionResult(
            success=False,
            message="You are not in active combat or a battle.",
        )


@dataclass
class PromoteSummonAction(Action):
    """Promote an ephemeral summon or charmed enemy into a Companion (#2502).

    Resolves a CombatOpponent from combat_opponent_id and an archetype from
    archetype_id. Two validation paths (see promote_summon_to_companion):
    summon-path (summoned_by + ALLY) or charmed-enemy-path (Charmed condition
    + source_character check). Charm difficulty reduction applies on the
    charmed-enemy path.
    """

    key: str = "promote_summon"
    name: str = "Promote Summon"
    icon: str = "sparkles"
    category: str = "companions"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HasCompanionCapacityPrerequisite()]

    def execute(self, actor, context=None, **kwargs) -> ActionResult:
        from world.combat.models import CombatOpponent  # noqa: PLC0415
        from world.companions.models import CompanionArchetype  # noqa: PLC0415
        from world.companions.services import (  # noqa: PLC0415
            PromoteSummonError,
            promote_summon_to_companion,
        )
        from world.magic.models.gifts import Gift  # noqa: PLC0415

        opponent_id = kwargs.get("combat_opponent_id")
        archetype_id = kwargs.get("archetype_id")
        gift_id = kwargs.get("gift_id")
        name = kwargs.get("name")
        if not opponent_id or not archetype_id or not gift_id or not name:
            return ActionResult(
                success=False,
                message="Pick a target, a gift, an archetype, and a name.",
            )

        opponent = CombatOpponent.objects.filter(pk=opponent_id).first()
        if opponent is None:
            return ActionResult(success=False, message="No such combat target.")
        archetype = CompanionArchetype.objects.get(pk=archetype_id)
        gift = Gift.objects.get(pk=gift_id)
        sheet = actor.sheet_data

        try:
            companion = promote_summon_to_companion(
                caster_sheet=sheet,
                combat_opponent=opponent,
                archetype=archetype,
                granting_gift=gift,
                name=name,
            )
        except PromoteSummonError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"{name} the {archetype.name} is now bonded to you.",
            data={"companion_id": companion.pk},
        )
