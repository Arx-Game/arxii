"""Battle lifecycle actions (#1592).

GM verbs (target_type=AREA, costs_turn=False) gate on being the scene GM or staff.
Player verb (target_type=SELF) gates on having an active BattleParticipant.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionContext, ActionResult, TargetType
from commands.utils.gm_resolution import resolve_account_or_none

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.battles.models import Battle


_NO_ACTIVE_BATTLE = "There is no active battle here."
_NO_GM_PERMISSION = "Only the battle's GM or staff can do that."
_NO_CHARACTER_SHEET = "You have no character sheet."
_NOT_IN_BATTLE = "You are not an active participant in a battle."


def _active_battle_in_room(actor: ObjectDB) -> Battle | None:
    """Return the newest non-concluded active Battle in *actor*'s room."""
    from world.battles.constants import BattleOutcome  # noqa: PLC0415
    from world.battles.models import Battle  # noqa: PLC0415

    room = actor.location
    if room is None:
        return None
    return (
        Battle.objects.filter(
            scene__location=room,
            scene__is_active=True,
            outcome=BattleOutcome.UNRESOLVED,
        )
        .select_related("scene")
        .order_by("-created_at")
        .first()
    )


def _actor_may_gm_battle(actor: ObjectDB, battle: Battle) -> bool:
    """True when *actor* is staff or the GM of *battle*'s scene."""
    account = resolve_account_or_none(actor)
    if account is None:
        return False
    if account.is_staff:
        return True
    return battle.scene.is_gm(account)


def _active_battle_for_gm(
    actor: ObjectDB,
) -> tuple[Battle | None, ActionResult | None]:
    """Return the active battle in *actor*'s room with GM permission checked."""
    battle = _active_battle_in_room(actor)
    if battle is None:
        return None, ActionResult(success=False, message=_NO_ACTIVE_BATTLE)
    if not _actor_may_gm_battle(actor, battle):
        return battle, ActionResult(success=False, message=_NO_GM_PERMISSION)
    return battle, None


@dataclass
class BeginBattleRoundAction(Action):
    """Open a new DECLARING round for the active battle (GM only)."""

    key: str = "begin_battle_round"
    name: str = "Begin Battle Round"
    icon: str = "play-circle"
    category: str = "battle"
    target_type: TargetType = TargetType.AREA
    costs_turn: bool = False

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.battles.exceptions import BattleError  # noqa: PLC0415
        from world.battles.services import begin_battle_round  # noqa: PLC0415

        battle, error = _active_battle_for_gm(actor)
        if error:
            return error

        try:
            battle_round = begin_battle_round(battle=battle)
        except BattleError as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=f"Round {battle_round.round_number} begins — declarations are open.",
        )


@dataclass
class ResolveBattleRoundAction(Action):
    """Resolve the current round of the active battle (GM only)."""

    key: str = "resolve_battle_round"
    name: str = "Resolve Battle Round"
    icon: str = "fast-forward"
    category: str = "battle"
    target_type: TargetType = TargetType.AREA
    costs_turn: bool = False

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.battles.exceptions import BattleError  # noqa: PLC0415
        from world.battles.resolution import resolve_battle_round  # noqa: PLC0415
        from world.battles.services import check_victory, conclude_battle  # noqa: PLC0415

        battle, error = _active_battle_for_gm(actor)
        if error:
            return error

        battle_round = battle.current_round
        if battle_round is None:
            return ActionResult(
                success=False,
                message="There is no active round to resolve.",
            )

        try:
            resolve_battle_round(battle_round=battle_round)
        except BattleError as exc:
            return ActionResult(success=False, message=exc.user_message)

        # Refresh and check victory after resolution.
        battle.refresh_from_db()
        outcome = check_victory(battle=battle)
        if outcome is not None:
            conclude_battle(battle=battle, outcome=outcome)
            return ActionResult(
                success=True,
                message=f"The round resolves. The battle concludes: {outcome}.",
            )

        return ActionResult(success=True, message="The round resolves.")


@dataclass
class ConcludeBattleAction(Action):
    """Force-conclude the active battle (GM only).

    Derives the outcome from the natural win condition first, then the timer
    rule, then defaults to DEFENDER_MARGINAL when neither applies.

    Note: When neither condition fires ("defenders hold" fallback), the outcome
    is DEFENDER_MARGINAL regardless of VP totals — check VP via check_victory first
    if a more precise outcome is needed before calling this action.
    """

    key: str = "conclude_battle"
    name: str = "Conclude Battle"
    icon: str = "stop-circle"
    category: str = "battle"
    target_type: TargetType = TargetType.AREA
    costs_turn: bool = False

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.battles.constants import BattleOutcome  # noqa: PLC0415
        from world.battles.services import (  # noqa: PLC0415
            check_victory,
            conclude_battle,
            maybe_conclude_on_timer,
        )

        battle, error = _active_battle_for_gm(actor)
        if error:
            return error

        # 1. Natural win condition.
        outcome = check_victory(battle=battle)
        if outcome is not None:
            conclude_battle(battle=battle, outcome=outcome)
        else:
            # 2. Timer rule (also calls conclude_battle internally if it fires).
            outcome = maybe_conclude_on_timer(battle=battle)
            if outcome is None:
                # 3. GM force: defenders hold by default.
                outcome = BattleOutcome.DEFENDER_MARGINAL
                conclude_battle(battle=battle, outcome=outcome)

        return ActionResult(
            success=True,
            message=f"The battle concludes: {outcome}.",
        )


@dataclass
class DeclareBattleActionAction(Action):
    """Declare a battle action (STRIKE or SUPPORT) for the current round."""

    key: str = "declare_battle_action"
    name: str = "Declare Battle Action"
    icon: str = "sword"
    category: str = "battle"
    target_type: TargetType = TargetType.SELF
    costs_turn: bool = False

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.battles.constants import (  # noqa: PLC0415
            BattleActionKind,
            BattleActionScope,
            BattleParticipantStatus,
        )
        from world.battles.exceptions import BattleError  # noqa: PLC0415
        from world.battles.models import BattleParticipant  # noqa: PLC0415
        from world.battles.services import declare_battle_action  # noqa: PLC0415
        from world.magic.models import Technique  # noqa: PLC0415

        # Resolve the actor's CharacterSheet via the reverse OneToOne accessor.
        try:
            sheet = actor.sheet_data
        except ObjectDoesNotExist:
            return ActionResult(success=False, message=_NO_CHARACTER_SHEET)

        # Find the character's active BattleParticipant.
        participant = (
            BattleParticipant.objects.filter(
                character_sheet=sheet,
                status=BattleParticipantStatus.ACTIVE,
                battle__scene__is_active=True,
            )
            .select_related("battle")
            .order_by("-battle__created_at")
            .first()
        )
        if participant is None:
            return ActionResult(success=False, message=_NOT_IN_BATTLE)

        technique_id = kwargs.get("technique_id")
        try:
            technique = Technique.objects.get(pk=technique_id)
        except Technique.DoesNotExist:
            return ActionResult(success=False, message="Technique not found.")

        action_kind = kwargs.get("action_kind", BattleActionKind.STRIKE)
        target_unit = kwargs.get("target_unit")
        target_ally = kwargs.get("target_ally")
        scope = kwargs.get("scope", BattleActionScope.UNIT)
        target_place = kwargs.get("target_place")
        target_side = kwargs.get("target_side")

        try:
            decl = declare_battle_action(
                participant=participant,
                action_kind=action_kind,
                technique=technique,
                target_unit=target_unit,
                target_ally=target_ally,
                scope=scope,
                target_place=target_place,
                target_side=target_side,
            )
        except BattleError as exc:
            return ActionResult(success=False, message=exc.user_message)

        kind_label = dict(BattleActionKind.choices).get(action_kind, action_kind)
        return ActionResult(
            success=True,
            message=f"You declare: {kind_label} ({technique.name}).",
            data={"declaration_id": decl.pk},
        )


@dataclass
class ChallengeChampionDuelAction(Action):
    """Issue a Champion duel at a BattlePlace against a GM-authored boss (#1710)."""

    key: str = "challenge_champion_duel"
    name: str = "Challenge Champion Duel"
    icon: str = "shield-alt"
    category: str = "battle"
    target_type: TargetType = TargetType.AREA
    costs_turn: bool = False

    def execute(  # noqa: PLR0911 - distinct guard failures read clearest as early returns
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.battles.exceptions import BattleError  # noqa: PLC0415
        from world.battles.models import BattleParticipant, BattlePlace  # noqa: PLC0415
        from world.battles.services import open_champion_duel  # noqa: PLC0415
        from world.combat.models import ThreatPool  # noqa: PLC0415

        try:
            sheet = actor.sheet_data
        except ObjectDoesNotExist:
            return ActionResult(success=False, message=_NO_CHARACTER_SHEET)

        battle_place_id = kwargs.get("battle_place_id")
        try:
            battle_place = BattlePlace.objects.select_related("battle__scene").get(
                pk=battle_place_id
            )
        except BattlePlace.DoesNotExist:
            return ActionResult(success=False, message="No such battle front.")

        participant = BattleParticipant.objects.filter(
            battle=battle_place.battle, character_sheet=sheet
        ).first()
        if participant is None:
            return ActionResult(success=False, message=_NOT_IN_BATTLE)

        opponent_kwargs = dict(kwargs.get("opponent_kwargs") or {})
        threat_pool_id = opponent_kwargs.get("threat_pool")
        if threat_pool_id is not None:
            try:
                opponent_kwargs["threat_pool"] = ThreatPool.objects.get(pk=threat_pool_id)
            except ThreatPool.DoesNotExist:
                return ActionResult(success=False, message="No such threat pool.")

        try:
            enc = open_champion_duel(
                battle_place=battle_place,
                challenger_participant=participant,
                opponent_kwargs=opponent_kwargs,
            )
        except BattleError as exc:
            return ActionResult(success=False, message=exc.user_message)
        except (TypeError, ValueError):
            return ActionResult(
                success=False, message="Could not open the duel — check the opponent details."
            )

        return ActionResult(
            success=True,
            message=f"You challenge the boss of {battle_place.name} to single combat!",
            data={"encounter_id": enc.pk},
        )
