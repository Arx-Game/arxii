"""GM combat-encounter lifecycle actions (#1494).

These actions expose the same lifecycle seams as the web ``CombatEncounterViewSet``
(begin round, resolve round, add/remove participants/opponents, pause, end, and
preview opponent defaults). They are gated to the encounter's scene GM or staff.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from actions.base import Action
from actions.prerequisites import MinimumGMLevelPrerequisite, Prerequisite
from actions.types import ActionContext, ActionResult, TargetType
from commands.exceptions import CommandError
from commands.utils.gm_resolution import (
    resolve_account_or_none,
    resolve_character_sheet_in_room,
    resolve_model_by_pk_or_name,
)
from world.combat.constants import OpponentTier
from world.gm.constants import GMLevel
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.areas.positioning.models import Position
    from world.combat.models import (
        CombatEncounter,
        CombatOpponent,
        CombatParticipant,
        CreatureTemplate,
    )
    from world.combat.scaling import OpponentStatBlock
    from world.scenes.models import Scene


# Encounter statuses that represent an ongoing (non-completed) combat.
_ACTIVE_ENCOUNTER_STATUSES: frozenset[str] = frozenset(
    {
        RoundStatus.DECLARING,
        RoundStatus.RESOLVING,
        RoundStatus.BETWEEN_ROUNDS,
    }
)

_NO_ACTIVE_ENCOUNTER = "There is no active encounter here."
_NO_GM_PERMISSION = "Only the scene's GM or staff can do that."
_NO_ACTIVE_SCENE = "There is no active scene here to start an encounter in."
_NO_SUCH_BEAT = "No such beat."
_NO_BEAT_PERMISSION = "Only that beat's story Lead GM or staff may route an encounter onto it."


def _encounter_in_room(
    actor: ObjectDB,
    *,
    statuses: frozenset[str] | None = None,
) -> CombatEncounter | None:
    """Return the newest combat encounter in *actor*'s room, optionally filtered by status."""
    from world.combat.models import CombatEncounter  # noqa: PLC0415

    room = actor.location
    if room is None:
        return None
    queryset = CombatEncounter.objects.filter(room=room)
    if statuses is not None:
        queryset = queryset.filter(status__in=statuses)
    return queryset.select_related("scene").order_by("-created_at").first()


def _active_encounter_in_room(actor: ObjectDB) -> CombatEncounter | None:
    """Return the newest non-completed combat encounter in *actor*'s room."""
    return _encounter_in_room(actor, statuses=_ACTIVE_ENCOUNTER_STATUSES)


def _latest_encounter_in_room(actor: ObjectDB) -> CombatEncounter | None:
    """Return the newest combat encounter in *actor*'s room, regardless of status."""
    return _encounter_in_room(actor)


def _actor_may_gm_encounter(actor: ObjectDB, encounter: CombatEncounter) -> bool:
    """True when *actor* is staff or the GM of *encounter*'s scene."""
    account = resolve_account_or_none(actor)
    if account is None:
        return False
    if account.is_staff:
        return True
    return encounter.scene.is_gm(account)


def _actor_may_start_encounter(actor: ObjectDB, scene: Scene) -> bool:
    """True when *actor* may create an encounter in *scene* (#3388).

    Delegates to ``world.combat.permissions.can_create_encounter_for_scene`` — the single
    predicate shared with the web create gate (see that function's docstring). Deliberately
    broader than ``_actor_may_gm_encounter`` (adds the scene co-owner branch) because
    creation is "may you administer this scene," not "are you this existing encounter's
    established GM."
    """
    from world.combat.permissions import can_create_encounter_for_scene  # noqa: PLC0415

    account = resolve_account_or_none(actor)
    if account is None:
        return False
    return can_create_encounter_for_scene(account, scene)


def _resolve_participant_in_encounter(
    encounter: CombatEncounter,
    value: str,
) -> CombatParticipant:
    """Resolve a participant by PK or by their character's display name."""
    from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist  # noqa: PLC0415

    from world.combat.models import CombatParticipant  # noqa: PLC0415

    queryset = CombatParticipant.objects.filter(encounter=encounter)
    not_found_msg = f"No participant named {value!r} in this encounter."

    try:
        if value.isdigit():
            participant = queryset.get(pk=value)
        else:
            participant = queryset.get(character_sheet__character__db_key__iexact=value)
    except (ObjectDoesNotExist, MultipleObjectsReturned) as exc:
        raise CommandError(not_found_msg) from exc

    return participant


def _resolve_opponent_in_encounter(
    encounter: CombatEncounter,
    value: str,
) -> CombatOpponent:
    """Resolve an ACTIVE opponent by PK or by case-insensitive exact name (#3382).

    Scoped to ``status=ACTIVE`` — a GM shouldn't "remove" an opponent that's
    already defeated/fled/removed. ``CombatOpponent.name`` is freehand text
    (not unique), so PK is tried first when the value is all-digits.
    """
    from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist  # noqa: PLC0415

    from world.combat.constants import OpponentStatus  # noqa: PLC0415
    from world.combat.models import CombatOpponent  # noqa: PLC0415

    queryset = CombatOpponent.objects.filter(encounter=encounter, status=OpponentStatus.ACTIVE)
    not_found_msg = f"No active opponent named {value!r} in this encounter."

    try:
        if value.isdigit():
            opponent = queryset.get(pk=value)
        else:
            opponent = queryset.get(name__iexact=value)
    except (ObjectDoesNotExist, MultipleObjectsReturned) as exc:
        raise CommandError(not_found_msg) from exc

    return opponent


def _permission_failure_result(encounter: CombatEncounter | None) -> ActionResult:
    """Return a consistent failure result when an actor lacks GM rights."""
    if encounter is None:
        return ActionResult(success=False, message=_NO_ACTIVE_ENCOUNTER)
    return ActionResult(success=False, message=_NO_GM_PERMISSION)


def _fetch_encounter_and_permission(
    actor: ObjectDB,
    fetch: Callable[[ObjectDB], CombatEncounter | None],
) -> tuple[CombatEncounter | None, ActionResult | None]:
    """Return the encounter plus an error result if *actor* may not GM it."""
    encounter = fetch(actor)
    if encounter is None:
        return None, ActionResult(success=False, message=_NO_ACTIVE_ENCOUNTER)
    if not _actor_may_gm_encounter(actor, encounter):
        return encounter, _permission_failure_result(encounter)
    return encounter, None


def _active_encounter_for_gm(
    actor: ObjectDB,
) -> tuple[CombatEncounter | None, ActionResult | None]:
    """Return the active encounter in *actor*'s room with GM permission checked."""
    return _fetch_encounter_and_permission(actor, _active_encounter_in_room)


@dataclass
class BeginEncounterRoundAction(Action):
    """Advance the active encounter from BETWEEN_ROUNDS to DECLARING."""

    key: str = "begin_encounter_round"
    name: str = "Begin Encounter Round"
    icon: str = "play-circle"
    category: str = "combat"
    target_type: TargetType = TargetType.AREA
    costs_turn: bool = False

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.combat.services import begin_declaration_phase  # noqa: PLC0415

        encounter, error = _fetch_encounter_and_permission(actor, _active_encounter_in_room)
        if error:
            return error

        try:
            begin_declaration_phase(encounter)
        except ValueError as err:
            return ActionResult(success=False, message=str(err))
        return ActionResult(success=True, message="Round begins.")


@dataclass
class ResolveEncounterRoundAction(Action):
    """Resolve the current round of the active encounter."""

    key: str = "resolve_encounter_round"
    name: str = "Resolve Encounter Round"
    icon: str = "fast-forward"
    category: str = "combat"
    target_type: TargetType = TargetType.AREA
    costs_turn: bool = False

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from actions.errors import ActionDispatchError  # noqa: PLC0415
        from world.combat.services import resolve_round  # noqa: PLC0415

        encounter, error = _active_encounter_for_gm(actor)
        if error:
            return error
        if encounter.status != RoundStatus.DECLARING:
            return ActionResult(
                success=False,
                message="The encounter is not gathering declarations.",
            )

        try:
            resolve_round(encounter)
        except (ValueError, ActionDispatchError) as err:
            return ActionResult(success=False, message=str(err))
        return ActionResult(success=True, message="The round resolves.")


def _resolve_add_opponent_inputs(
    kwargs: dict[str, Any],
) -> tuple[str, str, object, str, object] | ActionResult:
    """Resolve + validate ``AddOpponentAction`` kwargs.

    Returns ``(name, tier, threat_pool, description, position)`` on success,
    or the failure ``ActionResult`` to return immediately. Extracted from
    ``execute()`` to keep its own return-statement count low (PLR0911).
    """
    from world.areas.positioning.models import Position  # noqa: PLC0415
    from world.combat.models import ThreatPool  # noqa: PLC0415

    name = kwargs.get("name")
    tier = kwargs.get("tier")
    threat_pool_id = kwargs.get("threat_pool_id")
    description = kwargs.get("description", "")
    position_id = kwargs.get("position_id")

    if not name or not tier or threat_pool_id is None:
        return ActionResult(
            success=False,
            message="Name, tier, and threat pool are required.",
        )
    if tier not in OpponentTier.values:
        return ActionResult(success=False, message="Invalid opponent tier.")

    try:
        pool = resolve_model_by_pk_or_name(
            ThreatPool,
            str(threat_pool_id),
            not_found_msg=f"No threat pool named {threat_pool_id!r} found.",
        )
    except CommandError as err:
        return ActionResult(success=False, message=str(err))

    position = None
    if position_id is not None:
        try:
            position = Position.objects.get(pk=position_id)
        except Position.DoesNotExist:
            return ActionResult(success=False, message="That position does not exist.")

    return name, tier, pool, description, position


@dataclass
class AddOpponentAction(Action):
    """Add an NPC opponent to the active encounter."""

    key: str = "add_opponent"
    name: str = "Add Opponent"
    icon: str = "skull"
    category: str = "combat"
    target_type: TargetType = TargetType.AREA
    costs_turn: bool = False

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.areas.positioning.exceptions import PositionError  # noqa: PLC0415
        from world.combat.services import add_opponent  # noqa: PLC0415

        encounter, error = _active_encounter_for_gm(actor)
        if error:
            return error

        resolved = _resolve_add_opponent_inputs(kwargs)
        if isinstance(resolved, ActionResult):
            return resolved
        name, tier, pool, description, position = resolved

        # #2001 Task 5: threads the GM's account so add_opponent's custody
        # APPEAR gate can refuse an outsider GM spawning a story-protected
        # NPC (via existing_objectdb/persona — this action doesn't accept
        # either kwarg yet, so today's ephemeral-only spawns are never
        # gated, but the account is threaded here so any future kwarg
        # addition inherits the gate for free).
        account = resolve_account_or_none(actor)

        try:
            opponent = add_opponent(
                encounter,
                name=name,
                tier=tier,
                threat_pool=pool,
                description=description,
                acting_account=account,
                position=position,
            )
        except ValueError as err:
            return ActionResult(success=False, message=str(err))
        except PositionError as exc:
            # A position in a different room than the encounter's spawn room.
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=f"Opponent '{opponent.name}' added to the encounter.",
        )


def _resolve_spawn_creature_inputs(
    kwargs: dict[str, Any],
) -> tuple[CreatureTemplate, Position | None] | ActionResult:
    """Resolve + validate ``SpawnCreatureAction`` kwargs.

    Returns ``(template, position)`` on success, or the failure ``ActionResult``
    to return immediately. Mirrors ``_resolve_add_opponent_inputs``'s shape:
    ``template`` resolves pk-or-name via the shared ``resolve_model_by_pk_or_name``
    helper; ``position_id`` is a pk (name-to-pk resolution happens in the telnet
    command layer, exactly as ``_handle_add`` does for ``AddOpponentAction``).
    """
    from world.areas.positioning.models import Position  # noqa: PLC0415
    from world.combat.models import CreatureTemplate  # noqa: PLC0415

    template_ref = kwargs.get("template")
    position_id = kwargs.get("position_id")

    if not template_ref:
        return ActionResult(success=False, message="A creature template is required.")

    try:
        template = resolve_model_by_pk_or_name(
            CreatureTemplate,
            str(template_ref),
            not_found_msg=f"No creature template named {template_ref!r} found.",
        )
    except CommandError as err:
        return ActionResult(success=False, message=str(err))

    position = None
    if position_id is not None:
        try:
            position = Position.objects.get(pk=position_id)
        except Position.DoesNotExist:
            return ActionResult(success=False, message="That position does not exist.")

    return template, position


@dataclass
class SpawnCreatureAction(Action):
    """Spawn an authored ``CreatureTemplate`` bestiary entry into the active encounter (#3424).

    Mirrors ``AddOpponentAction``'s shape exactly: resolves the active encounter
    via ``_active_encounter_for_gm``, threads the GM's account through
    ``acting_account`` for the same custody APPEAR gate, and resolves
    ``position_id`` (a pk — name resolution happens in the telnet command layer,
    see ``CmdEncounter._handle_spawn``). Calls
    ``world.combat.services.spawn_from_creature_template``, which clones any
    authored ``CreaturePhaseTemplate``/``BreakBarConfig`` rows onto the spawned
    opponent — the wiring gap #3424 closes (the service previously had zero
    non-test callers).
    """

    key: str = "spawn_creature"
    name: str = "Spawn Creature"
    icon: str = "skull"
    category: str = "combat"
    target_type: TargetType = TargetType.AREA
    costs_turn: bool = False

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.areas.positioning.exceptions import PositionError  # noqa: PLC0415
        from world.combat.services import spawn_from_creature_template  # noqa: PLC0415

        encounter, error = _active_encounter_for_gm(actor)
        if error:
            return error

        resolved = _resolve_spawn_creature_inputs(kwargs)
        if isinstance(resolved, ActionResult):
            return resolved
        template, position = resolved

        # Same custody-threading rationale as AddOpponentAction: a spawned
        # bestiary opponent is ephemeral today (no existing_objectdb/persona
        # kwarg here yet), but the account is threaded through so a future
        # kwarg addition inherits the APPEAR gate for free.
        account = resolve_account_or_none(actor)

        try:
            opponent = spawn_from_creature_template(
                encounter,
                template,
                position=position,
                acting_account=account,
            )
        except ValueError as err:
            return ActionResult(success=False, message=str(err))
        except PositionError as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=f"'{opponent.name}' spawned from the bestiary.",
        )


@dataclass
class RemoveOpponentAction(Action):
    """Remove an NPC opponent from the active encounter (#3382)."""

    key: str = "remove_opponent"
    name: str = "Remove Opponent"
    icon: str = "skull-off"
    category: str = "combat"
    target_type: TargetType = TargetType.AREA
    costs_turn: bool = False

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        *,
        opponent_id: str | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.combat.services import remove_opponent  # noqa: PLC0415

        encounter, error = _active_encounter_for_gm(actor)
        if error:
            return error
        if opponent_id is None:
            return ActionResult(success=False, message="An opponent is required.")

        try:
            opponent = _resolve_opponent_in_encounter(encounter, str(opponent_id))
        except CommandError as err:
            return ActionResult(success=False, message=str(err))

        try:
            remove_opponent(opponent)
        except ValueError as err:
            return ActionResult(success=False, message=str(err))

        return ActionResult(
            success=True,
            message=f"Opponent '{opponent.name}' removed from the encounter.",
        )


@dataclass
class AddEncounterParticipantAction(Action):
    """Add a PC participant to the active encounter."""

    key: str = "add_encounter_participant"
    name: str = "Add Encounter Participant"
    icon: str = "user-plus"
    category: str = "combat"
    target_type: TargetType = TargetType.AREA
    costs_turn: bool = False

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        *,
        character_sheet_id: str | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.combat.services import add_participant  # noqa: PLC0415

        encounter, error = _active_encounter_for_gm(actor)
        if error:
            return error
        if character_sheet_id is None:
            return ActionResult(success=False, message="A character is required.")

        try:
            sheet = resolve_character_sheet_in_room(
                actor,
                str(character_sheet_id),
                room=encounter.room,
            )
        except CommandError as err:
            return ActionResult(success=False, message=str(err))

        try:
            add_participant(encounter, sheet)
        except ValueError as err:
            return ActionResult(success=False, message=str(err))

        return ActionResult(
            success=True,
            message=f"{sheet.character.db_key} added to the encounter.",
        )


@dataclass
class RemoveEncounterParticipantAction(Action):
    """Remove a PC participant from the active encounter."""

    key: str = "remove_encounter_participant"
    name: str = "Remove Encounter Participant"
    icon: str = "user-minus"
    category: str = "combat"
    target_type: TargetType = TargetType.AREA
    costs_turn: bool = False

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        *,
        participant_id: str | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.combat.services import remove_participant  # noqa: PLC0415

        encounter, error = _active_encounter_for_gm(actor)
        if error:
            return error
        if participant_id is None:
            return ActionResult(success=False, message="A participant is required.")

        try:
            participant = _resolve_participant_in_encounter(encounter, str(participant_id))
        except CommandError as err:
            return ActionResult(success=False, message=str(err))

        try:
            remove_participant(participant)
        except ValueError as err:
            return ActionResult(success=False, message=str(err))

        return ActionResult(
            success=True,
            message=f"{participant.character_sheet.character.db_key} removed from the encounter.",
        )


@dataclass
class PauseEncounterAction(Action):
    """Pause or resume the active encounter's timer."""

    key: str = "pause_encounter"
    name: str = "Pause Encounter"
    icon: str = "pause-circle"
    category: str = "combat"
    target_type: TargetType = TargetType.AREA
    costs_turn: bool = False

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        encounter, error = _active_encounter_for_gm(actor)
        if error:
            return error

        encounter.is_paused = not encounter.is_paused
        encounter.save(update_fields=["is_paused"])
        if encounter.is_paused:
            return ActionResult(success=True, message="Encounter paused.")
        return ActionResult(success=True, message="Encounter resumed.")


def _validate_encounter_settings_kwargs(
    kwargs: dict[str, Any],
) -> dict[str, Any] | ActionResult:
    """Validate + coerce ``UpdateEncounterSettingsAction`` kwargs.

    Returns the validated kwargs dict (``stakes_level``/``risk_level``/
    ``pace_mode``/parsed-int ``pace_timer_minutes``) on success, or the
    failure ``ActionResult`` to return immediately. Extracted from
    ``execute()`` to keep its own argument/return-statement counts low
    (PLR0913/PLR0911), mirroring ``_resolve_add_opponent_inputs``.
    """
    from world.combat.constants import PaceMode, RiskLevel, StakesLevel  # noqa: PLC0415

    stakes_level = kwargs.get("stakes_level")
    risk_level = kwargs.get("risk_level")
    pace_mode = kwargs.get("pace_mode")
    pace_timer_minutes = kwargs.get("pace_timer_minutes")

    if stakes_level is not None and stakes_level not in StakesLevel.values:
        return ActionResult(success=False, message="Invalid stakes level.")
    if risk_level is not None and risk_level not in RiskLevel.values:
        return ActionResult(success=False, message="Invalid risk level.")
    if pace_mode is not None and pace_mode not in PaceMode.values:
        return ActionResult(success=False, message="Invalid pace mode.")

    parsed_timer: int | None = None
    if pace_timer_minutes is not None:
        try:
            parsed_timer = int(pace_timer_minutes)
        except (TypeError, ValueError):
            return ActionResult(success=False, message="Timer minutes must be a whole number.")
        if parsed_timer < 1:
            return ActionResult(success=False, message="Timer minutes must be at least 1.")

    return {
        "stakes_level": stakes_level,
        "risk_level": risk_level,
        "pace_mode": pace_mode,
        "pace_timer_minutes": parsed_timer,
    }


@dataclass
class UpdateEncounterSettingsAction(Action):
    """GM: change stakes/risk/pace/timer on a live encounter (#3383).

    Mirrors ``PauseEncounterAction``'s shape: resolve the active encounter via
    ``_active_encounter_for_gm``, then call ``update_encounter_settings`` with
    whichever of the four kwargs was supplied. Telnet's four subverbs
    (``stakes``/``risk``/``pace``/``timer``) each supply exactly one.
    """

    key: str = "update_encounter_settings"
    name: str = "Update Encounter Settings"
    icon: str = "sliders"
    category: str = "combat"
    target_type: TargetType = TargetType.AREA
    costs_turn: bool = False

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.combat.services import update_encounter_settings  # noqa: PLC0415

        encounter, error = _active_encounter_for_gm(actor)
        if error:
            return error

        validated = _validate_encounter_settings_kwargs(kwargs)
        if isinstance(validated, ActionResult):
            return validated

        update_encounter_settings(encounter, **validated)
        return ActionResult(success=True, message="Encounter settings updated.")


@dataclass
class EndEncounterAction(Action):
    """Force-end the active encounter as ABANDONED."""

    key: str = "end_encounter"
    name: str = "End Encounter"
    icon: str = "stop-circle"
    category: str = "combat"
    target_type: TargetType = TargetType.AREA
    costs_turn: bool = False

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.combat.services import end_encounter  # noqa: PLC0415

        encounter, error = _fetch_encounter_and_permission(actor, _latest_encounter_in_room)
        if error:
            return error
        if encounter.status == RoundStatus.COMPLETED:
            return ActionResult(success=False, message="Encounter already completed.")

        try:
            end_encounter(encounter)
        except ValueError as err:
            return ActionResult(success=False, message=str(err))
        return ActionResult(success=True, message="Encounter ended.")


@dataclass
class PreviewOpponentDefaultsAction(Action):
    """Preview the scaling formula output for a tier without mutating state."""

    key: str = "preview_opponent_defaults"
    name: str = "Preview Opponent Defaults"
    icon: str = "eye"
    category: str = "combat"
    target_type: TargetType = TargetType.AREA
    costs_turn: bool = False

    def _tier_label(self, tier: str) -> str:
        return dict(OpponentTier.choices).get(tier, tier)

    def _format_preview(
        self,
        tier: str,
        block: OpponentStatBlock,
        stakes_ok: bool,
        stakes_message: str,
    ) -> str:
        lines = [
            f"Tier: {self._tier_label(tier)}",
            f"Max health: {block.max_health}",
            f"Soak: {block.soak_value}",
        ]
        if block.probing_threshold is not None:
            lines.append(f"Probing threshold: {block.probing_threshold}")
        if block.swarm_count is not None:
            lines.append(f"Swarm count: {block.swarm_count}")
        if block.body_toughness is not None:
            lines.append(f"Body toughness: {block.body_toughness}")
        if block.bodies_per_attack is not None:
            lines.append(f"Bodies per attack: {block.bodies_per_attack}")
        if block.barrier_strength is not None:
            lines.append(f"Barrier strength: {block.barrier_strength}")
        if block.phases:
            lines.append(f"Boss phases: {len(block.phases)}")
        if stakes_message:
            lines.append(f"Stakes gate: {stakes_message}")
        else:
            lines.append(f"Stakes gate: {'OK' if stakes_ok else 'Blocked'}")
        return "\n".join(lines)

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        *,
        tier: str | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.combat.models import OpponentTierTemplate  # noqa: PLC0415
        from world.combat.scaling import (  # noqa: PLC0415
            StakesRequirementError,
            compute_opponent_stat_block,
            validate_stakes_requirement,
        )

        encounter, error = _active_encounter_for_gm(actor)
        if error:
            return error
        if tier is None or tier not in OpponentTier.values:
            return ActionResult(success=False, message="Invalid opponent tier.")

        try:
            block = compute_opponent_stat_block(tier, encounter)
        except OpponentTierTemplate.DoesNotExist:
            return ActionResult(
                success=False,
                message="Scaling template for that tier is not configured.",
            )

        account = resolve_account_or_none(actor)
        stakes_ok = True
        stakes_message = ""
        if account is not None:
            try:
                validate_stakes_requirement(encounter, account)
            except StakesRequirementError as exc:
                stakes_ok = False
                stakes_message = exc.user_message

        message = self._format_preview(tier, block, stakes_ok, stakes_message)
        return ActionResult(success=True, message=message)


def _resolve_dramatic_beat_target(kwargs: dict[str, Any]) -> ObjectDB | None:
    """Resolve the ``target`` kwarg to an ``ObjectDB`` character (#3387).

    Mirrors ``gm_adjudication._resolve_gm_target``: telnet always passes an
    already-resolved ``ObjectDB``; the web REST dispatch path does no ObjectDB
    resolution of its own, so a plain int pk must be resolved here too.
    """
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    target = kwargs.get("target")
    if target is None or isinstance(target, ObjectDB):
        return target
    return ObjectDB.objects.filter(pk=target).first()


@dataclass
class GMTriggerDramaticBeatAction(Action):
    """SENIOR-gated manual trigger for ``apply_dramatic_surge`` on a named character (#3387).

    Ruled (2026-08-26, #3387): a GM cannot manually spotlight a dramatic beat the
    automatic detectors miss (``escalation.py``'s ally-peril/hated-foe/high-stakes/
    interference legs, ``engagement_locks.py``'s duel-interference leg) — every
    existing caller of ``apply_dramatic_surge`` is automatic. This is the ruled
    stopgap: gated at the same top trust tier as ``InvokeCatalogCheckAction``
    (SENIOR, staff bypass preserved) — "a staff stopgap, not a routine GM tool."

    Resolves the encounter via ``_active_encounter_for_gm`` (staff-or-scene-GM,
    same as every other action in this module), then the target
    ``CombatParticipant`` by ``character_sheet_id=target.pk`` — the
    ObjectDB/CharacterSheet shared-pk O2O. Deliberately does **not** reuse
    ``_resolve_participant_in_encounter``: that helper's ``value.isdigit()``
    branch treats a numeric string as a *participant* pk, not a character/
    ObjectDB pk, and would misresolve the id the web panel sends (the same trap
    ``gm_adjudication._resolve_gm_target``'s docstring documents for the sibling
    ``gm_apply_condition`` action).

    ``reason`` is required (fails loud like ``GMApplyConditionAction``'s
    ``condition_ref`` check) and is persisted onto the created
    ``DramaticSurgeRecord`` — staff-facing provenance, never broadcast to the
    room (the room only ever sees the existing generic surge narration
    template). The surge amount reuses the encounter's own authored
    ``escalation_curve.spike_intensity_amount`` when set, else the same
    fallback constant (``2``) that field itself defaults to.

    A repeat trigger on the same character in the same encounter is a dedup
    no-op at the ``DramaticSurgeRecord`` layer (matching ``HIGH_STAKES``'s
    existing one-shot behavior) — surfaced as a distinct refusal message, not a
    silently-reported success.
    """

    key: str = "gm_trigger_dramatic_beat"
    name: str = "Trigger Dramatic Beat"
    icon: str = "sparkles"
    category: str = "combat"
    target_type: TargetType = TargetType.SINGLE
    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target"})

    _DEFAULT_SURGE_AMOUNT = 2

    def get_prerequisites(self) -> list[Prerequisite]:
        return [MinimumGMLevelPrerequisite(GMLevel.SENIOR)]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.combat.constants import SurgeTriggerKind  # noqa: PLC0415
        from world.combat.escalation import apply_dramatic_surge  # noqa: PLC0415
        from world.combat.models import CombatParticipant  # noqa: PLC0415

        encounter, error = _active_encounter_for_gm(actor)
        if error:
            return error

        target = _resolve_dramatic_beat_target(kwargs)
        if target is None:
            return ActionResult(success=False, message="A target character is required.")

        reason = str(kwargs.get("reason") or "").strip()
        if not reason:
            return ActionResult(success=False, message="A reason is required.")

        participant = CombatParticipant.objects.filter(
            encounter=encounter, character_sheet_id=target.pk
        ).first()
        if participant is None:
            return ActionResult(
                success=False,
                message=f"{target.key} is not a participant in this encounter.",
            )

        curve = encounter.escalation_curve
        amount = curve.spike_intensity_amount if curve is not None else self._DEFAULT_SURGE_AMOUNT

        beat = apply_dramatic_surge(
            encounter=encounter,
            participant=participant,
            amount=amount,
            trigger_kind=SurgeTriggerKind.GM_MANUAL,
            subject_sheet=None,
            reason=reason,
        )
        if beat is None:
            return ActionResult(
                success=False,
                message=f"{target.key} has already been spotlighted in this encounter.",
            )

        return ActionResult(
            success=True,
            message=f"The dramatic spotlight turns to {target.key}.",
        )


@dataclass
class CreateEncounterAction(Action):
    """Start a new combat encounter in the actor's current scene (#3388)."""

    key: str = "create_encounter"
    name: str = "Create Encounter"
    icon: str = "swords"
    category: str = "combat"
    target_type: TargetType = TargetType.SELF
    costs_turn: bool = False

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        *,
        pace_mode: str | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.combat.constants import PaceMode  # noqa: PLC0415
        from world.combat.models import CombatEncounter  # noqa: PLC0415
        from world.combat.services import finalize_new_encounter  # noqa: PLC0415
        from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415
        from world.stories.models import Beat  # noqa: PLC0415
        from world.stories.permissions import account_may_route_beat  # noqa: PLC0415

        scene = get_active_scene(actor.location)
        if scene is None:
            return ActionResult(success=False, message=_NO_ACTIVE_SCENE)
        if not _actor_may_start_encounter(actor, scene):
            return ActionResult(success=False, message=_NO_GM_PERMISSION)

        resolved_pace_mode = PaceMode.TIMED
        if pace_mode is not None:
            if pace_mode not in PaceMode.values:
                return ActionResult(success=False, message="Invalid pace mode.")
            resolved_pace_mode = pace_mode

        beat = None
        beat_id = kwargs.get("beat_id")
        if beat_id is not None:
            try:
                beat = Beat.objects.filter(pk=beat_id).first()
            except (TypeError, ValueError):
                beat = None
            if beat is None:
                return ActionResult(success=False, message=_NO_SUCH_BEAT)
            if not account_may_route_beat(resolve_account_or_none(actor), beat):
                return ActionResult(success=False, message=_NO_BEAT_PERMISSION)

        encounter = CombatEncounter.objects.create(
            scene=scene, pace_mode=resolved_pace_mode, story_beat=beat
        )
        finalize_new_encounter(encounter)
        return ActionResult(
            success=True,
            message=f"Encounter #{encounter.pk} begins ({resolved_pace_mode} pace).",
        )
