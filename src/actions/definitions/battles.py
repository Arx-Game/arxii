"""Battle lifecycle actions (#1592).

GM verbs (target_type=AREA, costs_turn=False) gate on being the scene GM or staff.
Player verb (target_type=SELF) gates on having an active BattleParticipant.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.prerequisites import MinimumGMLevelPrerequisite, Prerequisite
from actions.types import ActionContext, ActionResult, TargetType
from commands.utils.gm_resolution import resolve_account_or_none
from world.gm.constants import GMLevel

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
    """Declare a battle action (any BattleActionKind) for the current round."""

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
        target_fortification = kwargs.get("target_fortification")
        reposition_dx = kwargs.get("reposition_dx")
        reposition_dy = kwargs.get("reposition_dy")

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
                target_fortification=target_fortification,
                reposition_dx=reposition_dx,
                reposition_dy=reposition_dy,
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


@dataclass
class OpenPlaceEncounterAction(Action):
    """Open a general party encounter at a BattlePlace (#2008).

    GM verb, battle-scoped — re-verifies ``_actor_may_gm_battle`` (mirrors
    ``EnlistBattleParticipantAction``). Thin wrapper over
    ``world.battles.services.open_place_encounter``.
    """

    key: str = "open_place_encounter"
    name: str = "Open Front Encounter"
    icon: str = "swords"
    category: str = "battle"
    target_type: TargetType = TargetType.AREA
    costs_turn: bool = False

    def get_prerequisites(self) -> list[Prerequisite]:
        return [MinimumGMLevelPrerequisite(GMLevel.JUNIOR)]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.battles.exceptions import BattleError  # noqa: PLC0415
        from world.battles.models import BattlePlace  # noqa: PLC0415
        from world.battles.services import open_place_encounter  # noqa: PLC0415

        battle_place_id = kwargs.get("battle_place_id")
        try:
            battle_place = BattlePlace.objects.select_related("battle__scene").get(
                pk=battle_place_id
            )
        except (BattlePlace.DoesNotExist, TypeError, ValueError):
            return ActionResult(success=False, message=_NO_SUCH_PLACE)

        if not _actor_may_gm_battle(actor, battle_place.battle):
            return ActionResult(success=False, message=_NO_GM_PERMISSION)

        try:
            enc = open_place_encounter(battle_place=battle_place)
        except BattleError as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=f"You open a fight at {battle_place.name}!",
            data={"encounter_id": enc.pk},
        )


@dataclass
class JoinPlaceEncounterAction(Action):
    """Join a party encounter open at a stationed BattlePlace (#2008).

    Player verb (unlike the GM-gated ``OpenPlaceEncounterAction``). Enforces that
    the actor's ``BattleParticipant`` is actually stationed at the target place —
    ``world.combat.services.join_encounter`` has no such check (ADR-0010: battles
    depends on combat, never the reverse, so the stationing check can't live
    there).
    """

    key: str = "join_place_encounter"
    name: str = "Join Front Encounter"
    icon: str = "swords"
    category: str = "battle"
    target_type: TargetType = TargetType.SELF

    def execute(  # noqa: PLR0911 - distinct guard failures read clearest as early returns
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.battles.constants import BattleParticipantStatus  # noqa: PLC0415
        from world.battles.models import BattleParticipant, BattlePlace  # noqa: PLC0415
        from world.combat.beat_wiring import activate_stakes_for_scene  # noqa: PLC0415
        from world.combat.constants import EncounterType  # noqa: PLC0415
        from world.combat.services import join_encounter  # noqa: PLC0415

        try:
            sheet = actor.sheet_data
        except ObjectDoesNotExist:
            return ActionResult(success=False, message=_NO_CHARACTER_SHEET)

        battle_place_id = kwargs.get("battle_place_id")
        try:
            battle_place = BattlePlace.objects.select_related("battle", "combat_encounter").get(
                pk=battle_place_id
            )
        except (BattlePlace.DoesNotExist, TypeError, ValueError):
            return ActionResult(success=False, message=_NO_SUCH_PLACE)

        if battle_place.combat_encounter_id is None:
            return ActionResult(success=False, message="No encounter is open at that front.")
        if battle_place.combat_encounter.encounter_type != EncounterType.PARTY_COMBAT:
            return ActionResult(
                success=False, message="This front's encounter isn't open for general joining."
            )

        participant = BattleParticipant.objects.filter(
            battle=battle_place.battle,
            character_sheet=sheet,
            status=BattleParticipantStatus.ACTIVE,
        ).first()
        if participant is None:
            return ActionResult(success=False, message=_NOT_IN_BATTLE)
        if participant.place_id != battle_place.id:
            return ActionResult(success=False, message="You aren't stationed at that front.")

        encounter = battle_place.combat_encounter
        try:
            join_encounter(encounter, sheet)
        except ValueError as exc:
            return ActionResult(success=False, message=str(exc))

        activate_stakes_for_scene(encounter.scene, [sheet])

        return ActionResult(
            success=True,
            message=f"You join the fight at {battle_place.name}!",
            data={"encounter_id": encounter.pk},
        )


# ---------------------------------------------------------------------------
# #2010 — GM battle staging: JUNIOR-gated REGISTRY actions turning a catalog
# pick (BattleMapBlueprint/BattleUnitTemplate) into a live Battle. Unlike the
# room-scoped GM verbs above (target_type=AREA, "the active battle here"),
# these five are target_type=SELF and kwargs-driven on explicit ids -- a GM
# builds a battle via kwargs rather than by standing over it. Battles remain
# location-less at the service layer by default (ADR-0081); CreateBattleAction
# binds the new battle's backing Scene to the staging GM's current room
# (``stage_battle(location=actor.location)``) so it is immediately reachable
# by the room-scoped verbs above via ``_active_battle_in_room``.
# ---------------------------------------------------------------------------

_NO_SUCH_BATTLE = "No such battle."
_NO_SUCH_BLUEPRINT = "No such active battle-map blueprint."
_NO_SUCH_TEMPLATE = "No such active battle-unit template."
_NO_SUCH_SIDE = "No such side on this battle."
_NO_SUCH_PLACE = "No such place on this battle."


def _format_catalog_row(pk: int, name: str, description: str) -> str:
    snippet = (description or "").strip()
    row = f"[{pk}] {name}"
    return f"{row} -- {snippet}" if snippet else row


@dataclass
class CreateBattleAction(Action):
    """Create a new Battle, optionally staged from a catalog blueprint (#2010).

    JUNIOR-trust GM verb -- the entry point of the staging pipeline. Wraps
    ``world.battles.staging.stage_battle``; when ``blueprint_id`` is given, the
    blueprint's places/fortifications are cloned onto the new battle in the same
    call. Also grants the creating account ``is_gm`` on the battle's backing
    Scene (unrelated to a room -- see the module-level note above) so the later
    battle-scoped actions' ``_actor_may_gm_battle`` recognizes this GM as the
    battle's own, not merely staff.

    ``blueprint_id``, when given, is resolved against ``is_active=True`` only --
    mirroring ``InvokeCatalogCheckAction``'s ``CheckType`` resolution
    (``gm_adjudication.py``): a catalog row retired from the browsing surface
    stays unreachable by id too, not just hidden from search.
    """

    key: str = "create_battle"
    name: str = "Create Battle"
    icon: str = "flag"
    category: str = "battle"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [MinimumGMLevelPrerequisite(GMLevel.JUNIOR)]

    def execute(  # noqa: PLR0911, C901 - distinct guard failures read clearest as early returns
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from django.db import transaction  # noqa: PLC0415

        from world.battles.exceptions import BattleStagingError  # noqa: PLC0415
        from world.battles.models import BattleMapBlueprint  # noqa: PLC0415
        from world.battles.staging import stage_battle  # noqa: PLC0415
        from world.combat.constants import RiskLevel  # noqa: PLC0415
        from world.scenes.models import SceneParticipation  # noqa: PLC0415

        name = str(kwargs.get("name") or "").strip()
        if not name:
            return ActionResult(success=False, message="Name the battle.")

        risk_level = kwargs.get("risk_level") or RiskLevel.LOW
        if risk_level not in RiskLevel.values:
            return ActionResult(
                success=False,
                message="Pick a risk level: " + ", ".join(RiskLevel.values) + ".",
            )

        blueprint = None
        blueprint_id = kwargs.get("blueprint_id")
        if blueprint_id is not None:
            try:
                blueprint = BattleMapBlueprint.objects.get(pk=blueprint_id, is_active=True)
            except (BattleMapBlueprint.DoesNotExist, TypeError, ValueError):
                return ActionResult(success=False, message=_NO_SUCH_BLUEPRINT)

        campaign_story = None
        campaign_story_id = kwargs.get("campaign_story_id")
        if campaign_story_id is not None:
            from world.stories.models import Story  # noqa: PLC0415

            try:
                campaign_story = Story.objects.get(pk=campaign_story_id)
            except (Story.DoesNotExist, TypeError, ValueError):
                return ActionResult(success=False, message="No such story.")

        region = None
        region_id = kwargs.get("region_id")
        if region_id is not None:
            from world.areas.models import Area  # noqa: PLC0415

            try:
                region = Area.objects.get(pk=region_id)
            except (Area.DoesNotExist, TypeError, ValueError):
                return ActionResult(success=False, message="No such region.")

        try:
            with transaction.atomic():
                battle = stage_battle(
                    name=name,
                    risk_level=risk_level,
                    blueprint=blueprint,
                    campaign_story=campaign_story,
                    region=region,
                    location=actor.location,
                )

                account = resolve_account_or_none(actor)
                if account is not None:
                    SceneParticipation.objects.update_or_create(
                        scene=battle.scene,
                        account=account,
                        defaults={"is_gm": True},
                    )
        except BattleStagingError as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=f"Battle '{battle.name}' created.",
            data={"battle_id": battle.pk, "scene_id": battle.scene_id},
        )


@dataclass
class StageBattleMapAction(Action):
    """Clone a catalog BattleMapBlueprint's places/fortifications onto a Battle (#2010).

    JUNIOR-trust GM verb, battle-scoped -- re-verifies ``_actor_may_gm_battle``
    in ``execute`` since ``MinimumGMLevelPrerequisite`` alone only proves
    general JUNIOR+ trust, not standing over *this* battle. A JUNIOR GM who
    isn't staff and isn't this battle's own GM must not restage someone else's
    battle. Wraps ``world.battles.staging.instantiate_battle_blueprint``.
    """

    key: str = "stage_battle_map"
    name: str = "Stage Battle Map"
    icon: str = "map"
    category: str = "battle"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [MinimumGMLevelPrerequisite(GMLevel.JUNIOR)]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.battles.exceptions import BattleStagingError  # noqa: PLC0415
        from world.battles.models import Battle, BattleMapBlueprint  # noqa: PLC0415
        from world.battles.staging import instantiate_battle_blueprint  # noqa: PLC0415

        battle_id = kwargs.get("battle_id")
        try:
            battle = Battle.objects.select_related("scene").get(pk=battle_id)
        except (Battle.DoesNotExist, TypeError, ValueError):
            return ActionResult(success=False, message=_NO_SUCH_BATTLE)

        if not _actor_may_gm_battle(actor, battle):
            return ActionResult(success=False, message=_NO_GM_PERMISSION)

        blueprint_id = kwargs.get("blueprint_id")
        try:
            blueprint = BattleMapBlueprint.objects.get(pk=blueprint_id, is_active=True)
        except (BattleMapBlueprint.DoesNotExist, TypeError, ValueError):
            return ActionResult(success=False, message=_NO_SUCH_BLUEPRINT)

        replace = bool(kwargs.get("replace", False))

        try:
            places = instantiate_battle_blueprint(blueprint, battle, replace=replace)
        except BattleStagingError as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=f"Staged {len(places)} place(s) from '{blueprint.name}'.",
            data={"place_ids": [place.pk for place in places]},
        )


@dataclass
class SpawnBattleUnitsAction(Action):
    """Spawn one or more BattleUnits from a catalog BattleUnitTemplate (#2010).

    JUNIOR-trust GM verb, battle-scoped -- re-verifies ``_actor_may_gm_battle``
    (see ``StageBattleMapAction``). Wraps
    ``world.battles.staging.spawn_units_from_template``; ``count`` is clamped
    server-side to ``MAX_TEMPLATE_SPAWN`` by that service.
    """

    key: str = "spawn_battle_units"
    name: str = "Spawn Battle Units"
    icon: str = "users"
    category: str = "battle"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [MinimumGMLevelPrerequisite(GMLevel.JUNIOR)]

    def execute(  # noqa: PLR0911 - distinct guard failures read clearest as early returns
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.battles.models import (  # noqa: PLC0415
            Battle,
            BattlePlace,
            BattleSide,
            BattleUnitTemplate,
        )
        from world.battles.staging import spawn_units_from_template  # noqa: PLC0415

        battle_id = kwargs.get("battle_id")
        try:
            battle = Battle.objects.select_related("scene").get(pk=battle_id)
        except (Battle.DoesNotExist, TypeError, ValueError):
            return ActionResult(success=False, message=_NO_SUCH_BATTLE)

        if not _actor_may_gm_battle(actor, battle):
            return ActionResult(success=False, message=_NO_GM_PERMISSION)

        template_id = kwargs.get("template_id")
        try:
            template = BattleUnitTemplate.objects.get(pk=template_id, is_active=True)
        except (BattleUnitTemplate.DoesNotExist, TypeError, ValueError):
            return ActionResult(success=False, message=_NO_SUCH_TEMPLATE)

        side_id = kwargs.get("side_id")
        try:
            side = BattleSide.objects.get(pk=side_id, battle=battle)
        except (BattleSide.DoesNotExist, TypeError, ValueError):
            return ActionResult(success=False, message=_NO_SUCH_SIDE)

        place = None
        place_id = kwargs.get("place_id")
        if place_id is not None:
            try:
                place = BattlePlace.objects.get(pk=place_id, battle=battle)
            except (BattlePlace.DoesNotExist, TypeError, ValueError):
                return ActionResult(success=False, message=_NO_SUCH_PLACE)

        try:
            count = int(kwargs.get("count") or 1)
        except (TypeError, ValueError):
            return ActionResult(success=False, message="Give a valid count.")

        units = spawn_units_from_template(
            template, battle=battle, side=side, place=place, count=count
        )

        return ActionResult(
            success=True,
            message=f"Spawned {len(units)} unit(s) from '{template.name}'.",
            data={"unit_ids": [unit.pk for unit in units]},
        )


@dataclass
class EnlistBattleParticipantAction(Action):
    """Enlist a player character in a Battle on one side (#2010).

    JUNIOR-trust GM verb, battle-scoped -- re-verifies ``_actor_may_gm_battle``
    (see ``StageBattleMapAction``). Thin wrapper over
    ``world.battles.services.enlist_participant``; pre-checks for an existing
    ``BattleParticipant`` row rather than surfacing the
    ``unique_battle_participant`` constraint's IntegrityError.
    """

    key: str = "enlist_battle_participant"
    name: str = "Enlist Battle Participant"
    icon: str = "user-plus"
    category: str = "battle"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [MinimumGMLevelPrerequisite(GMLevel.JUNIOR)]

    def execute(  # noqa: PLR0911 - distinct guard failures read clearest as early returns
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.battles.models import (  # noqa: PLC0415
            Battle,
            BattleParticipant,
            BattlePlace,
            BattleSide,
        )
        from world.battles.services import enlist_participant  # noqa: PLC0415
        from world.character_sheets.models import CharacterSheet  # noqa: PLC0415

        battle_id = kwargs.get("battle_id")
        try:
            battle = Battle.objects.select_related("scene").get(pk=battle_id)
        except (Battle.DoesNotExist, TypeError, ValueError):
            return ActionResult(success=False, message=_NO_SUCH_BATTLE)

        if not _actor_may_gm_battle(actor, battle):
            return ActionResult(success=False, message=_NO_GM_PERMISSION)

        character_sheet_id = kwargs.get("character_sheet_id")
        try:
            character_sheet = CharacterSheet.objects.get(pk=character_sheet_id)
        except (CharacterSheet.DoesNotExist, TypeError, ValueError):
            return ActionResult(success=False, message="No such character sheet.")

        side_id = kwargs.get("side_id")
        try:
            side = BattleSide.objects.get(pk=side_id, battle=battle)
        except (BattleSide.DoesNotExist, TypeError, ValueError):
            return ActionResult(success=False, message=_NO_SUCH_SIDE)

        place = None
        place_id = kwargs.get("place_id")
        if place_id is not None:
            try:
                place = BattlePlace.objects.get(pk=place_id, battle=battle)
            except (BattlePlace.DoesNotExist, TypeError, ValueError):
                return ActionResult(success=False, message=_NO_SUCH_PLACE)

        if BattleParticipant.objects.filter(
            battle=battle, character_sheet=character_sheet
        ).exists():
            return ActionResult(
                success=False,
                message=f"{character_sheet} is already enlisted in this battle.",
            )

        participant = enlist_participant(
            battle=battle, character_sheet=character_sheet, side=side, place=place
        )

        return ActionResult(
            success=True,
            message=f"{character_sheet} enlisted on {side.get_role_display()}.",
            data={"participant_id": participant.pk},
        )


@dataclass
class BrowseBattleCatalogAction(Action):
    """Search the BattleMapBlueprint/BattleUnitTemplate catalogs by name (#2010).

    JUNIOR-trust GM verb, read-only, not battle-scoped -- never selects,
    composes, or writes any catalog id; a GM discovers a blueprint/template's
    id here, then passes it to ``create_battle``/``stage_battle_map``/
    ``spawn_battle_units``. Both catalogs are filtered ``is_active=True`` --
    the one surface this feature's visibility rule is actually enforced on,
    since the staging services underneath (Task 2) deliberately do not check
    it themselves.
    """

    key: str = "browse_battle_catalog"
    name: str = "Browse Battle Catalog"
    icon: str = "search"
    category: str = "battle"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [MinimumGMLevelPrerequisite(GMLevel.JUNIOR)]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from django.db.models import Q  # noqa: PLC0415

        from world.battles.models import BattleMapBlueprint, BattleUnitTemplate  # noqa: PLC0415

        term = str(kwargs.get("term") or "").strip()

        blueprints = BattleMapBlueprint.objects.filter(is_active=True)
        templates = BattleUnitTemplate.objects.filter(is_active=True)
        if term:
            blueprints = blueprints.filter(Q(name__icontains=term) | Q(description__icontains=term))
            templates = templates.filter(Q(name__icontains=term) | Q(descriptor__icontains=term))

        lines: list[str] = []
        if blueprints.exists():
            lines.append("Battle-map blueprints:")
            lines.extend(_format_catalog_row(bp.pk, bp.name, bp.description) for bp in blueprints)
        if templates.exists():
            if lines:
                lines.append("")
            lines.append("Battle-unit templates:")
            lines.extend(
                _format_catalog_row(tmpl.pk, tmpl.name, tmpl.descriptor) for tmpl in templates
            )

        if not lines:
            message = f"No catalog entries matched {term!r}." if term else "The catalog is empty."
            return ActionResult(success=True, message=message)

        return ActionResult(success=True, message="\n".join(lines))
